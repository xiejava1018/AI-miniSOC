"""TP-Link Collector CLI 入口"""

import asyncio
import argparse
import signal
import sys
import os
import logging

from collector_framework.config import CollectorConfig
from collector_framework.sync_client import MiniSOCClient
from collector_framework.base import DataType
from tplink_collector.collector import TPLinkCollector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="TP-Link 路由器数据采集器")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--once", action="store_true", help="单次执行")
    parser.add_argument("--test", action="store_true", help="测试连通性")
    parser.add_argument("--interval", type=int, help="覆盖采集间隔（秒）")
    args = parser.parse_args()

    config = CollectorConfig.from_yaml(args.config)
    if args.once:
        config.once = True
    if args.interval:
        config.interval = args.interval

    router_cfg = config.extra.get("router", {})
    collector = TPLinkCollector(
        host=os.getenv("ROUTER_HOST", router_cfg.get("host", "192.168.0.1")),
        username=os.getenv("ROUTER_USERNAME", router_cfg.get("username", "")),
        password=os.getenv("ROUTER_PASSWORD", router_cfg.get("password", "")),
        port=int(os.getenv("ROUTER_PORT", router_cfg.get("port", 80))),
    )
    soc_client = MiniSOCClient(
        base_url=config.minisoc_url,
        api_key=config.minisoc_api_key,
    )

    if args.test:
        ok_router = asyncio.run(collector.test_connection())
        ok_soc = asyncio.run(soc_client.health_check())
        print(f"路由器连通性: {'OK' if ok_router else 'FAIL'}")
        print(f"AI-miniSOC 连通性: {'OK' if ok_soc else 'FAIL'}")
        asyncio.run(soc_client.close())
        sys.exit(0 if (ok_router and ok_soc) else 1)

    async def run_once():
        logger.info("开始采集...")
        result = await collector.collect(DataType.ASSET)
        logger.info(f"采集完成: {len(result.items)} 条")
        sync_result = await soc_client.sync(
            source=result.source,
            data_type=result.data_type.value,
            items=result.items,
            metadata=result.metadata,
        )
        logger.info(f"同步结果: {sync_result}")

    if config.once:
        asyncio.run(run_once())
        asyncio.run(soc_client.close())
    else:
        shutdown = asyncio.Event()

        def _signal_handler(*_):
            shutdown.set()

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        async def loop():
            while not shutdown.is_set():
                try:
                    await run_once()
                except Exception as e:
                    logger.error(f"采集失败: {e}", exc_info=True)
                try:
                    await asyncio.wait_for(shutdown.wait(), timeout=config.interval)
                except asyncio.TimeoutError:
                    pass

        logger.info(f"启动定时采集，间隔 {config.interval}s")
        asyncio.run(loop())
        asyncio.run(soc_client.close())


if __name__ == "__main__":
    main()
