"""TP-Link Collector 实现"""

import logging
from collector_framework.base import BaseCollector, DataType, CollectResult
from tplink_collector.client import TPLinkSLPClient

logger = logging.getLogger(__name__)


class TPLinkCollector(BaseCollector):
    """TP-Link 路由器数据采集器"""

    source_name = "tplink-router"
    supported_types = [DataType.ASSET]

    def __init__(self, host: str, username: str, password: str, port: int = 80):
        self.client = TPLinkSLPClient(host, username, password, port)

    async def collect(self, data_type: DataType) -> CollectResult:
        if data_type == DataType.ASSET:
            return await self._collect_assets()
        raise ValueError(f"不支持的数据类型: {data_type}")

    async def _collect_assets(self) -> CollectResult:
        """采集在线终端设备列表"""
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
            await self.client.logout()

    async def test_connection(self) -> bool:
        try:
            await self.client.login()
            await self.client.logout()
            return True
        except Exception as e:
            logger.error(f"路由器连通性测试失败: {e}")
            return False
