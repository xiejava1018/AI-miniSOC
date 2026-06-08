"""
Wazuh 采集器主类

从 Wazuh SIEM 采集资产、漏洞、基线数据并推送到 AI-miniSOC。
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from collector_framework.base import BaseCollector, CollectResult, DataType
from collector_framework.sync_client import MiniSOCClient
from collector_framework.config import CollectorConfig

from .wazuh_client import WazuhClient
from .transformers import (
    convert_agent_to_asset,
    convert_vuln_to_asset_vulnerability,
    convert_sca_to_baseline,
)

logger = logging.getLogger(__name__)


class WazuhCollector(BaseCollector):
    """Wazuh 数据采集器"""

    source_name = "wazuh"
    supported_types = [DataType.ASSET, DataType.VULNERABILITY, DataType.BASELINE]

    def __init__(self, config: CollectorConfig):
        self.config = config

        # 从 extra 配置中提取 Wazuh 连接信息
        wazuh_cfg = config.extra.get("wazuh", {})
        self.wazuh_url = wazuh_cfg.get(
            "url", config.extra.get("WAZUH_URL", "https://192.168.0.40:55000")
        )
        self.wazuh_user = wazuh_cfg.get(
            "user", config.extra.get("WAZUH_USER", "wazuh-wui")
        )
        self.wazuh_password = wazuh_cfg.get(
            "password", config.extra.get("WAZUH_PASSWORD", "")
        )

        # 创建客户端
        self.wazuh_client = WazuhClient(
            base_url=self.wazuh_url,
            username=self.wazuh_user,
            password=self.wazuh_password,
            verify_ssl=wazuh_cfg.get("verify_ssl", False),
        )
        self.sync_client = MiniSOCClient(
            base_url=config.minisoc_url,
            api_key=config.minisoc_api_key,
        )

    async def collect(self, data_type: DataType) -> CollectResult:
        """执行采集"""
        logger.info(f"开始采集 Wazuh {data_type.value} 数据")

        items = []
        metadata = {}

        try:
            if data_type == DataType.ASSET:
                items = await self._collect_assets()
            elif data_type == DataType.VULNERABILITY:
                items = await self._collect_vulnerabilities()
            elif data_type == DataType.BASELINE:
                items = await self._collect_baselines()
            else:
                raise ValueError(f"不支持的数据类型: {data_type}")

            logger.info(f"采集完成，共 {len(items)} 条数据")
            return CollectResult(
                source=self.source_name,
                data_type=data_type,
                items=items,
                collected_at=datetime.now(),
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"采集失败: {e}", exc_info=True)
            raise

    async def test_connection(self) -> bool:
        """测试 Wazuh API 连接"""
        try:
            return await self.wazuh_client.test_connection()
        except Exception as e:
            logger.error(f"连接测试失败: {e}")
            return False

    async def _collect_assets(self) -> list[dict]:
        """采集资产数据"""
        agents = await self.wazuh_client.get_agents()
        logger.info(f"获取到 {len(agents)} 个 agents")

        assets = []
        for agent in agents:
            asset = convert_agent_to_asset(agent)
            if asset:
                assets.append(asset)

        logger.info(f"成功转换 {len(assets)} 个资产")
        return assets

    async def _collect_vulnerabilities(self) -> list[dict]:
        """采集漏洞数据"""
        vulns = await self.wazuh_client.get_all_vulnerabilities()
        logger.info(f"获取到 {len(vulns)} 个漏洞")

        vulnerabilities = []
        for vuln in vulns:
            item = convert_vuln_to_asset_vulnerability(vuln)
            if item:
                vulnerabilities.append(item)

        logger.info(f"成功转换 {len(vulnerabilities)} 个漏洞")
        return vulnerabilities

    async def _collect_baselines(self) -> list[dict]:
        """采集基线数据"""
        sca_results = await self.wazuh_client.get_all_sca_results()
        logger.info(f"获取到 {len(sca_results)} 个 SCA 结果")

        baselines = []
        for sca in sca_results:
            item = convert_sca_to_baseline(sca)
            if item:
                baselines.append(item)

        logger.info(f"成功转换 {len(baselines)} 个基线")
        return baselines

    async def close(self):
        """关闭客户端连接"""
        await self.sync_client.close()


async def run_collector(config: CollectorConfig) -> None:
    """运行采集器（支持定时循环）"""
    collector = WazuhCollector(config)

    # 确定要采集的类型
    collect_types = config.collect_types or ["asset", "vulnerability", "baseline"]
    data_types = [DataType(t) for t in collect_types]

    logger.info(f"Wazuh Collector 启动，采集类型: {collect_types}")

    # 健康检查
    if not await collector.test_connection():
        logger.error("Wazuh API 连接失败，请检查配置")
        return

    # 主循环
    while True:
        for data_type in data_types:
            try:
                result = await collector.collect(data_type)

                # 推送到 AI-miniSOC
                sync_result = await collector.sync_client.sync(
                    source=result.source,
                    data_type=result.data_type.value,
                    items=result.items,
                    metadata=result.metadata,
                )
                logger.info(f"同步成功: {sync_result}")

            except Exception as e:
                logger.error(f"处理 {data_type.value} 失败: {e}")

        # 单次模式则退出
        if config.once:
            logger.info("单次模式完成，退出")
            break

        # 等待下次采集
        logger.info(f"等待 {config.interval} 秒后进行下次采集...")
        await asyncio.sleep(config.interval)

    await collector.close()
