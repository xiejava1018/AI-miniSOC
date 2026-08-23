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


# ---------------------------------------------------------------------------
# 【硬约束：本文件每次进程调用只允许出现一次 asyncio.run】
#
# MiniSOCClient 与 TPLinkSLPClient 都在 __init__ 里就构造了 httpx.AsyncClient，
# 而连接池 / transport 会在首次使用时绑定到当时正在运行的那个事件循环。
# 一旦分多次 asyncio.run，第二个循环里调 aclose() 就会去关挂在第一个（已关闭）
# 循环上的 transport，触发：
#     RuntimeError: Event loop is closed
#       at asyncio/selector_events.py  self._loop.call_soon(...)
#
# 生产实测代价（2026-08-08 ~ 08-23）：--test 分支连开 3 个循环，导致 docker
# HEALTHCHECK 连续失败 20531 次、容器整整 14 天 unhealthy —— 而路由器登录和
# 后端 /health 其实都返回 200，采集主循环一直正常。**纯粹是收尾代码把自己
# 判死了**，还顺带每次留下无人回收的 healthcheck 子进程（233 个僵尸）。
#
# 对照写法见 wazuh/src/wazuh_collector/__main__.py：全部步骤放进一个协程、
# 只 asyncio.run 一次，所以 wazuh-collector 始终 healthy。
# 新增分支时务必沿用「一个协程做完全部事情 + 单次 asyncio.run」的形状。
# ---------------------------------------------------------------------------


async def _aclose_all(collector: TPLinkCollector, soc_client: MiniSOCClient) -> None:
    """在同一个事件循环内释放两个 httpx 客户端。

    单个失败不影响另一个：收尾阶段的异常不应该覆盖掉主流程的结果
    （原实现就是被收尾异常带崩，把成功的检查报成了失败）。
    """
    for name, obj in (("router", collector), ("minisoc", soc_client)):
        try:
            await obj.close()
        except Exception as e:  # noqa: BLE001
            logger.warning(f"关闭 {name} 客户端失败（忽略）: {e}")


def _install_signal_handlers(shutdown: asyncio.Event) -> None:
    """优先用 loop.add_signal_handler，回调在事件循环内执行。

    signal.signal 的回调会在任意字节码边界触发，此时去动 asyncio.Event 的
    内部状态并不安全；add_signal_handler 是 Unix 上的正确做法。
    """
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, shutdown.set)
        except NotImplementedError:
            # 非 Unix 平台（如 Windows）不支持，退回 signal.signal
            signal.signal(sig, lambda *_: shutdown.set())


async def _collect_and_sync(
    collector: TPLinkCollector, soc_client: MiniSOCClient
) -> None:
    """采集一轮并推送到 AI-miniSOC。"""
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


async def _run_test(
    collector: TPLinkCollector, soc_client: MiniSOCClient
) -> int:
    """连通性自检（docker HEALTHCHECK 走这条路径）。"""
    try:
        ok_router = await collector.test_connection()
        ok_soc = await soc_client.health_check()
        print(f"路由器连通性: {'OK' if ok_router else 'FAIL'}")
        print(f"AI-miniSOC 连通性: {'OK' if ok_soc else 'FAIL'}")
        return 0 if (ok_router and ok_soc) else 1
    finally:
        await _aclose_all(collector, soc_client)


async def _run_once(
    collector: TPLinkCollector, soc_client: MiniSOCClient
) -> int:
    """单次采集。异常照旧向上抛，由 asyncio.run 打出 traceback 并非 0 退出。"""
    try:
        await _collect_and_sync(collector, soc_client)
        return 0
    finally:
        await _aclose_all(collector, soc_client)


async def _run_daemon(
    collector: TPLinkCollector, soc_client: MiniSOCClient, interval: int
) -> int:
    """定时采集常驻模式。"""
    shutdown = asyncio.Event()
    _install_signal_handlers(shutdown)
    logger.info(f"启动定时采集，间隔 {interval}s")
    try:
        while not shutdown.is_set():
            try:
                await _collect_and_sync(collector, soc_client)
            except Exception as e:  # noqa: BLE001
                # 单轮失败不中断常驻循环：路由器/后端临时不可达是常态
                logger.error(f"采集失败: {e}", exc_info=True)
            try:
                await asyncio.wait_for(shutdown.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
        logger.info("收到停止信号，正在退出...")
        return 0
    finally:
        await _aclose_all(collector, soc_client)


def main() -> None:
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

    # 每个分支恰好一次 asyncio.run —— 见文件头部硬约束说明
    if args.test:
        exit_code = asyncio.run(_run_test(collector, soc_client))
    elif config.once:
        exit_code = asyncio.run(_run_once(collector, soc_client))
    else:
        exit_code = asyncio.run(_run_daemon(collector, soc_client, config.interval))

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
