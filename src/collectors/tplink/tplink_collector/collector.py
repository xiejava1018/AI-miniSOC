"""TP-Link Collector 实现"""

import logging
from collector_framework.base import BaseCollector, DataType, CollectResult
from tplink_collector.client import TPLinkSLPClient

logger = logging.getLogger(__name__)


class TPLinkCollector(BaseCollector):
    """TP-Link 路由器数据采集器"""

    source_name = "tplink-router"
    supported_types = [DataType.ASSET, DataType.NAT_MAPPING]

    def __init__(self, host: str, username: str, password: str, port: int = 80):
        self.client = TPLinkSLPClient(host, username, password, port)

    async def collect(self, data_type: DataType) -> CollectResult:
        if data_type == DataType.ASSET:
            return await self._collect_assets()
        if data_type == DataType.NAT_MAPPING:
            return await self._collect_nat_rules()
        raise ValueError(f"不支持的数据类型: {data_type}")

    async def collect_session(
        self, data_types: list[DataType]
    ) -> list[CollectResult]:
        """一次 login + 一次 logout，包多种数据类型采集。

        设计动机（2026-10-12）：生产路由器 Web 登录有防爆破节流（5 分钟
        限 1 次），但其实“成功登录”本身也会被记入路由器告警（通知级别），
        刷频到 5 分钟 2 条会干扰运维看板。原实现每个数据类型独立
        login/logout（5 分钟 2 次登录），本方法 1 次 login 共享 stok
        给多个 get_* 调用，1 个 cycle 只产生 1 条“成功登录”通知。

        限制：data_types 里出现的项必须在 ``supported_types`` 里且不能重复。
        失败语义：login 阶段异常（认证失败 / 网络不通）会被外层
        ``_collect_and_sync`` 捕获后记日志、不中断下次循环；中途某个
        get_* 报 401（stok 被路由器主动作废）会在 client.get_* 里重新
        login 自愈，代价是本轮多 1 次登录。
        """
        unsupported = [t for t in data_types if t not in self.supported_types]
        if unsupported:
            raise ValueError(f"不支持的数据类型: {unsupported}")
        if len(set(data_types)) != len(data_types):
            raise ValueError(f"data_types 含重复项: {data_types}")

        await self.client.login()
        try:
            results: list[CollectResult] = []
            for dt in data_types:
                if dt == DataType.ASSET:
                    results.append(await self._collect_assets(skip_login=True))
                elif dt == DataType.NAT_MAPPING:
                    results.append(
                        await self._collect_nat_rules(skip_login=True)
                    )
            return results
        finally:
            await self.client.logout()

    async def _collect_assets(self, skip_login: bool = False) -> CollectResult:
        """采集在线终端设备列表。

        skip_login=True 时假定已登录（stok 可用）。典型场景：
        collect_session() 1 次 login 后调本方法 2 次。这种情况下
        client.get_hosts 内部如果遭遇 401（stok 被路由器作废）会自
        动重 login，故本方法不额外地再调 login。
        """
        if not skip_login:
            await self.client.login()
        try:
            hosts = await self.client.get_hosts()
            return CollectResult(
                source=self.source_name,
                data_type=DataType.ASSET,
                items=hosts,
                metadata={"host_count": len(hosts)},
            )
        finally:
            if not skip_login:
                await self.client.logout()

    async def _collect_nat_rules(
        self, skip_login: bool = False
    ) -> CollectResult:
        """采集虚拟服务器（DNAT 端口映射）规则。S2 暴露面归位数据源。

        skip_login 语义同 _collect_assets。
        """
        if not skip_login:
            await self.client.login()
        try:
            rules = await self.client.get_nat_rules()
            return CollectResult(
                source=self.source_name,
                data_type=DataType.NAT_MAPPING,
                items=rules,
                metadata={"nat_rule_count": len(rules)},
            )
        finally:
            if not skip_login:
                await self.client.logout()

    async def test_connection(self) -> bool:
        try:
            await self.client.login()
            await self.client.logout()
            return True
        except Exception as e:
            logger.error(f"路由器连通性测试失败: {e}")
            return False

    async def close(self) -> None:
        """释放底层 httpx 客户端。

        BaseCollector 没有定义 close()，此前谁都没关过路由器侧的
        AsyncClient（test_tplink.py 调 collector.close() 其实会 AttributeError）。
        必须与调用方在同一个事件循环内 await —— 原因见 __main__.py 头部说明。
        """
        await self.client.close()
