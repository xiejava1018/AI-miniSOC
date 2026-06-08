#!/usr/bin/env python3
"""
Wazuh Collector 入口脚本

支持:
- --once: 单次执行
- --interval: 采集间隔（秒）
- --test: 测试连接
- --types: 指定采集类型（逗号分隔）
"""

import asyncio
import argparse
import logging
import sys
from pathlib import Path

# 添加 src 到路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from collector_framework.config import CollectorConfig
from wazuh_collector.collector import WazuhCollector, run_collector

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Wazuh Collector for AI-miniSOC")
    parser.add_argument(
        "--config",
        default="/etc/wazuh-collector/config.yaml",
        help="配置文件路径",
    )
    parser.add_argument(
        "--once", action="store_true", help="单次执行后退出"
    )
    parser.add_argument(
        "--interval", type=int, help="采集间隔（秒），覆盖配置文件"
    )
    parser.add_argument(
        "--test", action="store_true", help="测试连接"
    )
    parser.add_argument(
        "--types",
        help="采集类型（逗号分隔）: asset,vulnerability,baseline",
    )

    args = parser.parse_args()

    # 加载配置
    try:
        config = CollectorConfig.from_yaml(args.config)
    except Exception as e:
        logger.error(f"加载配置文件失败: {e}")
        sys.exit(1)

    # 命令行参数覆盖
    if args.once:
        config.once = True
    if args.interval:
        config.interval = args.interval
    if args.types:
        config.collect_types = [t.strip() for t in args.types.split(",")]

    # 测试模式
    if args.test:
        logger.info("测试连接模式...")
        asyncio.run(test_connection(config))
        return

    # 运行采集器
    try:
        asyncio.run(run_collector(config))
    except KeyboardInterrupt:
        logger.info("收到中断信号，退出...")
    except Exception as e:
        logger.error(f"运行失败: {e}", exc_info=True)
        sys.exit(1)


async def test_connection(config: CollectorConfig):
    """测试连接"""
    collector = WazuhCollector(config)

    logger.info(f"测试 Wazuh API 连接: {collector.wazuh_url}")
    wazuh_ok = await collector.test_connection()
    logger.info(f"Wazuh API: {'✓ 连接成功' if wazuh_ok else '✗ 连接失败'}")

    logger.info(f"测试 AI-miniSOC 连接: {config.minisoc_url}")
    minisoc_ok = await collector.sync_client.health_check()
    logger.info(f"AI-miniSOC: {'✓ 连接成功' if minisoc_ok else '✗ 连接失败'}")

    await collector.close()

    if wazuh_ok and minisoc_ok:
        logger.info("所有连接测试通过 ✓")
        sys.exit(0)
    else:
        logger.error("部分连接测试失败 ✗")
        sys.exit(1)


if __name__ == "__main__":
    main()
