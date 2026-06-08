#!/usr/bin/env python3
"""
Wazuh Collector 持续运行脚本
"""

import asyncio
import logging
import sys
from pathlib import Path

# 添加路径
sys.path.insert(0, str(Path(__file__).parent / "src"))
sys.path.insert(0, str(Path(__file__).parent.parent / "base"))

from collector_framework.config import CollectorConfig
from collector_framework.base import DataType
from wazuh_collector.collector import WazuhCollector

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run_collector_loop():
    """持续运行采集器"""
    # 配置
    config = CollectorConfig(
        minisoc_url="http://192.168.0.128:8000",
        minisoc_api_key="sk-minisoc-wazuh-test2024",
        interval=300,  # 5分钟
        collect_types=["asset"],
        once=False,
        extra={
            "wazuh": {
                "url": "https://192.168.0.40:55000",
                "user": "wazuh",
                "password": "OgdHes6S57Y?L5HwU0dLB3tWtw.1.TUu",
                "verify_ssl": False,
            }
        }
    )

    logger.info("=" * 50)
    logger.info("Wazuh Collector 启动")
    logger.info(f"  AI-miniSOC: {config.minisoc_url}")
    logger.info(f"  Wazuh: {config.extra['wazuh']['url']}")
    logger.info(f"  采集间隔: {config.interval}秒")
    logger.info("=" * 50)

    collector = WazuhCollector(config)

    # 测试连接
    logger.info("测试连接...")
    wazuh_ok = await collector.test_connection()
    if not wazuh_ok:
        logger.error("Wazuh API 连接失败")
        return

    minisoc_ok = await collector.sync_client.health_check()
    if not minisoc_ok:
        logger.error("AI-miniSOC 连接失败")
        return

    logger.info("连接测试通过")

    # 持续采集循环
    while True:
        try:
            # 采集资产数据
            logger.info("采集资产数据...")
            result = await collector.collect(DataType.ASSET)
            logger.info(f"采集到 {len(result.items)} 条资产")

            # 同步到 AI-miniSOC
            if result.items:
                sync_result = await collector.sync_client.sync(
                    source=result.source,
                    data_type=result.data_type.value,
                    items=result.items,
                )
                logger.info(f"同步结果: {sync_result}")

            logger.info(f"等待 {config.interval} 秒...")

        except Exception as e:
            logger.error(f"采集失败: {e}", exc_info=True)

        # 等待下一次采集
        await asyncio.sleep(config.interval)


if __name__ == "__main__":
    try:
        asyncio.run(run_collector_loop())
    except KeyboardInterrupt:
        logger.info("收到中断信号，退出...")