"""ARL-Next Collector 实现（OH-ARL.1）。"""

import logging
from typing import ClassVar

from collector_framework.base import BaseCollector, CollectResult, DataType

from arl_collector.client import ARLClient

logger = logging.getLogger(__name__)


class ARLCollector(BaseCollector):
    """ARL-Next 攻击面测绘数据采集器（只读，不触发扫描）。

    source_name='arl-next'：SOC 侧 soc_asset_sources.source / 漏洞 scanner /
    发现 discovery_source 统一用此值（design §5.3/§5.5）。
    """

    source_name = "arl-next"
    supported_types: ClassVar[list[DataType]] = [DataType.ARL_SITE, DataType.ARL_VULN]

    def __init__(self, client: ARLClient, scope_ids: list[str] | None = None):
        self.client = client
        # scope 白名单（C1 授权范围）：None/空 = 拉全部归档资产组（单租户
        # 内部部署可接受）；配置后只拉白名单 scope，越界目标不进入管道。
        self.scope_ids = [s for s in (scope_ids or []) if s.strip()]

    async def _iter_scopes(self):
        if self.scope_ids:
            for sid in self.scope_ids:
                yield sid
        else:
            yield None

    async def collect(self, data_type: DataType) -> CollectResult:
        if data_type == DataType.ARL_SITE:
            return await self._collect(self.client.collect_sites, data_type)
        if data_type == DataType.ARL_VULN:
            return await self._collect(self.client.collect_vulns, data_type)
        raise ValueError(f"不支持的数据类型: {data_type}")

    async def _collect(self, fn, data_type: DataType) -> CollectResult:
        items: list[dict] = []
        meta: dict = {"scopes": self.scope_ids or ["*all*"]}
        skip_total = 0
        async for sid in self._iter_scopes():
            batch = await fn(scope_id=sid)
            items.extend(batch)
            m = getattr(self.client, "_last_sites_meta", None) \
                if data_type == DataType.ARL_SITE \
                else getattr(self.client, "_last_vulns_meta", None)
            if m and sid is not None:
                meta[f"scope:{sid}"] = m
            if m:
                skip_total += m.get("skipped_domain_only", 0)
        if skip_total:
            meta["skipped_domain_only"] = skip_total
        return CollectResult(
            source=self.source_name,
            data_type=data_type,
            items=items,
            metadata=meta,
        )

    async def test_connection(self) -> bool:
        try:
            await self.client.login()
            # 轻探一个归档端点（size=1）验证 token + code 判据
            await self.client.fetch_page("asset_site", page=1, size=1)
            return True
        except Exception as e:  # noqa: BLE001
            logger.error("ARL 连通性测试失败: %s", e)
            return False

    async def close(self) -> None:
        await self.client.close()
