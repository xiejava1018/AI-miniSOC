#!/usr/bin/env python3
"""TP-Link Collector 持续运行脚本 - 增强版"""

import asyncio
import logging
import os
import signal
import sys
import traceback
from pathlib import Path
from datetime import datetime

# 添加路径
sys.path.insert(0, str(Path(__file__).parent / "tplink_collector"))
sys.path.insert(0, str(Path(__file__).parent.parent / "base"))

from collector_framework.config import CollectorConfig
from collector_framework.sync_client import MiniSOCClient
from collector_framework.base import DataType
from tplink_collector.collector import TPLinkCollector

# 日志配置 - 同时输出到文件和控制台
log_file = "/tmp/tplink-collector.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


async def run():
    """运行采集器"""
    # 配置
    router_host = os.getenv("ROUTER_HOST", "192.168.0.1")
    router_user = os.getenv("ROUTER_USERNAME", "tploginadmin")
    router_pass = os.getenv("ROUTER_PASSWORD", "")
    minisoc_url = os.getenv("MINISOC_URL", "http://192.168.0.128:8000")
    minisoc_key = os.getenv("MINISOC_API_KEY", "sk-minisoc-wazuh-test2024")
    interval = int(os.getenv("TPLINK_INTERVAL", "300"))

    if not router_pass:
        logger.error("需要设置 ROUTER_PASSWORD 环境变量")
        sys.exit(1)

    logger.info("=" * 60)
    logger.info("TP-Link Collector 启动")
    logger.info(f"  路由器: {router_host}")
    logger.info(f"  AI-miniSOC: {minisoc_url}")
    logger.info(f"  采集间隔: {interval}秒")
    logger.info("=" * 60)

    collector = TPLinkCollector(
        host=router_host,
        username=router_user,
        password=router_pass,
    )
    soc_client = MiniSOCClient(base_url=minisoc_url, api_key=minisoc_key)

    # 测试连接
    logger.info("测试连接...")
    router_ok = await collector.test_connection()
    if not router_ok:
        logger.error("路由器连接失败，5秒后重试...")
        await asyncio.sleep(5)
        router_ok = await collector.test_connection()
        if not router_ok:
            logger.error("路由器连接失败，退出")
            sys.exit(1)
    soc_ok = await soc_client.health_check()
    if not soc_ok:
        logger.error("AI-miniSOC 连接失败，5秒后重试...")
        await asyncio.sleep(5)
        soc_ok = await soc_client.health_check()
        if not soc_ok:
            logger.error("AI-miniSOC 连接失败，退出")
            sys.exit(1)
    logger.info("连接测试通过")

    # 持续采集循环
    shutdown = asyncio.Event()
    consecutive_errors = 0
    max_consecutive_errors = 5

    def signal_handler(*_):
        logger.info("收到中断信号...")
        shutdown.set()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    while not shutdown.is_set():
        try:
            # 采集数据
            logger.info("采集在线设备...")
            result = await collector.collect(DataType.ASSET)
            logger.info(f"采集到 {len(result.items)} 台设备")
            consecutive_errors = 0  # 成功后重置错误计数

            # 同步到 AI-miniSOC
            if result.items:
                sync_result = await soc_client.sync(
                    source=result.source,
                    data_type=result.data_type.value,
                    items=result.items,
                )
                logger.info(f"同步结果: 创建={sync_result.get('created', 0)}, 更新={sync_result.get('updated', 0)}, 跳过={sync_result.get('skipped', 0)}")

            logger.info(f"等待 {interval} 秒...")

        except asyncio.TimeoutError:
            logger.warning(f"采集超时，当前时间: {datetime.now()}")
            consecutive_errors += 1
        except Exception as e:
            consecutive_errors += 1
            error_msg = f"采集失败 [{consecutive_errors}/{max_consecutive_errors}]: {str(e)}"
            logger.error(error_msg)
            # 打印详细堆栈
            logger.error(f"堆栈: {traceback.format_exc()}")

            # 连续错误过多时退出
            if consecutive_errors >= max_consecutive_errors:
                logger.error(f"连续 {max_consecutive_errors} 次错误，退出采集器")
                break

        try:
            await asyncio.wait_for(shutdown.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass

    await soc_client.close()
    logger.info("采集器退出")


if __name__ == "__main__":
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        logger.info("收到中断信号，退出...")
    except Exception as e:
        logger.error(f"未捕获的异常: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
