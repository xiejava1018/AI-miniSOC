"""ARL Collector CLI 入口（OH-ARL.1）。

【硬约束：本文件每次进程调用只允许出现一次 asyncio.run】——
照 tplink __main__.py 头部说明（2026-08 生产事故：healthcheck 多次
asyncio.run 导致 Event loop is closed + 20531 次 unhealthy）。
全部步骤放进一个协程，只 asyncio.run 一次。
"""

import argparse
import asyncio
import logging
import os
import signal
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "base"))

from collector_framework.base import DataType
from collector_framework.sync_client import MiniSOCClient

from arl_collector.client import ARLClient
from arl_collector.collector import ARLCollector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_S = 1800  # 30min（design §6.1）


def _build() -> tuple[ARLCollector, MiniSOCClient]:
    """从 env 构建采集器与 SOC 客户端（env 注入，gitignore；照 tplink 模式）。"""
    base_url = os.getenv("ARL_BASE_URL", "")
    if not base_url:
        raise ValueError("缺少 ARL_BASE_URL")
    api_key = os.getenv("ARL_API_KEY") or None
    username = os.getenv("ARL_USERNAME") or None
    password = os.getenv("ARL_PASSWORD") or None
    scope_ids = [
        s.strip() for s in (os.getenv("ARL_SCOPE_IDS") or "").split(",") if s.strip()
    ]
    verify_tls = os.getenv("ARL_VERIFY_TLS", "false").lower() == "true"

    client = ARLClient(
        base_url=base_url,
        username=username,
        password=password,
        api_key=api_key,
        verify_tls=verify_tls,
    )
    collector = ARLCollector(client, scope_ids)

    soc_url = os.getenv("MINISOC_URL", "")
    soc_key = os.getenv("MINISOC_API_KEY", "")
    if not soc_url or not soc_key:
        raise ValueError("缺少 MINISOC_URL / MINISOC_API_KEY")
    soc = MiniSOCClient(soc_url, soc_key)
    return collector, soc


async def _aclose_all(collector: ARLCollector, soc: MiniSOCClient) -> None:
    for name, obj in (("arl", collector), ("minisoc", soc)):
        try:
            await obj.close()
        except Exception as e:  # noqa: BLE001
            logger.warning("关闭 %s 客户端失败（忽略）: %s", name, e)


async def _collect_and_sync(
    collector: ARLCollector, soc: MiniSOCClient,
) -> None:
    """采集一轮并推送 arl_site + arl_vuln 两种数据类型。

    单次 HTTP 仅承载一个 data_type，故分两次 sync。
    """
    for dt in (DataType.ARL_SITE, DataType.ARL_VULN):
        try:
            result = await collector.collect(dt)
            logger.info(
                "ARL %s 采集完成: %d 条 (meta=%s)",
                dt.value, len(result.items), result.metadata,
            )
            if not result.items:
                continue
            sync_result = await soc.sync(
                source=result.source,
                data_type=result.data_type.value,
                items=result.items,
                metadata=result.metadata,
            )
            logger.info("ARL %s 同步结果: %s", dt.value, sync_result)
        except Exception as e:  # noqa: BLE001
            # 单类型失败不拖挂另一类型（照 tplink _collect_and_sync 语义）
            logger.error("ARL %s 采集/同步失败: %s", dt.value, e)


async def _run_test(collector: ARLCollector, soc: MiniSOCClient) -> int:
    """连通性自检（docker HEALTHCHECK 走这条路径）。"""
    try:
        ok_arl = await collector.test_connection()
        ok_soc = await soc.health_check()
        print(f"ARL 连通性: {'OK' if ok_arl else 'FAIL'}")
        print(f"AI-miniSOC 连通性: {'OK' if ok_soc else 'FAIL'}")
        return 0 if (ok_arl and ok_soc) else 1
    finally:
        await _aclose_all(collector, soc)


async def _run_once(collector: ARLCollector, soc: MiniSOCClient) -> int:
    try:
        await _collect_and_sync(collector, soc)
        return 0
    finally:
        await _aclose_all(collector, soc)


async def _run_daemon(
    collector: ARLCollector, soc: MiniSOCClient, interval_s: int,
) -> int:
    shutdown = asyncio.Event()

    def _on_signal(*_):
        shutdown.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _on_signal)

    exit_code = 0
    try:
        logger.info("ARL collector 守护启动，间隔 %ds", interval_s)
        while not shutdown.is_set():
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=interval_s)
                break  # 收到退出信号
            except asyncio.TimeoutError:
                pass
            try:
                await _collect_and_sync(collector, soc)
            except Exception as e:  # noqa: BLE001
                logger.error("采集周期失败（不中断循环）: %s", e)
        logger.info("收到退出信号，ARL collector 退出")
    finally:
        await _aclose_all(collector, soc)
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description="ARL-Next → AI-miniSOC 采集器")
    parser.add_argument("--test", action="store_true", help="连通性自检后退出")
    parser.add_argument("--once", action="store_true", help="采集一轮后退出")
    parser.add_argument(
        "--interval", type=int,
        default=int(os.getenv("ARL_SYNC_INTERVAL_S", DEFAULT_INTERVAL_S)),
        help="守护模式采集间隔秒数（默认 1800）",
    )
    args = parser.parse_args()

    collector, soc = _build()

    # 单 asyncio.run 硬约束：全部步骤在一个协程里完成
    async def _entry() -> int:
        if args.test:
            return await _run_test(collector, soc)
        if args.once:
            return await _run_once(collector, soc)
        return await _run_daemon(collector, soc, args.interval)

    return asyncio.run(_entry())


if __name__ == "__main__":
    sys.exit(main())
