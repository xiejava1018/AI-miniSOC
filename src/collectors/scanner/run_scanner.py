#!/usr/bin/env python3
"""
scanner-collector CLI 入口（P3/F-S2 + 控制面集成）

Phase 1 + Phase 2 设计（final.md §6 + §7.4）：
  - --once  单次扫描 + 推送（开发调试 / cron 触发）—— 无心跳、无拉任务
  - --loop  拉模型循环（每30s heartbeat + 每10s 拉任务 + 跑 nmap + 推数据 + 回写）

环境变量（生产由 docker-compose env 注入）：
  - MINISOC_URL            AI-miniSOC 地址
  - MINISOC_API_KEY        普通 API Key（心跳、推数据、/scan/tasks/* 拉模型都用这个）
  - SCANNER_ID             拉模型需要的 scanner_id（控制面 /scan/agents/heartbeat 必填）
  - SCAN_PUBLIC_TARGETS    --once 模式的目标
  - HEARTBEAT_INTERVAL     默认30s
  - POLL_INTERVAL          默认10s

注意：Phase 1 用的 MINISOC_API_KEY 同时承担「普通采集器」+「扫描器」身份。
Phase 2 推荐生产用独立 SCANNER_API_KEY（控制面 /scan/agents 创建 scanner 时分配）。
当前实现：单 Key 走通全链路，Phase 4 改造成双 Key。
"""

import argparse
import asyncio
import logging
import os
import sys
import uuid as uuidlib
from pathlib import Path

# 加载 .env（开发用；生产由 docker-compose env 注入）
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from collector_framework.base import DataType
from collector_framework.sync_client import MiniSOCClient

from scanner_collector.collector import ScannerCollector


# 配置应用日志
logging.basicConfig(
    level=os.getenv("SCANNER_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================================
# --once 模式：单次跑（Phase 1 行为，cron / 手动触发）
# ============================================================================
async def run_once(collector: ScannerCollector, client: MiniSOCClient) -> int:
    """执行一次扫描 + 推送 + 退出。"""
    logger.info("=== scanner-collector --once: starting single scan ===")
    try:
        result = await collector.collect(DataType.PORT)
    except (NotImplementedError, RuntimeError) as e:
        logger.error("collect failed: %s", e)
        return 1

    items = result.items
    logger.info(
        "collected %d items from %d hosts (task_uuid=%s)",
        len(items),
        result.metadata.get("scanned_targets", 0),
        result.metadata.get("scan_task_uuid", "?"),
    )
    if not items:
        return 0

    try:
        await client.sync(
            source="scanner-port",
            data_type="port",
            items=items,
            metadata=result.metadata,
        )
        return 0
    except RuntimeError as e:
        logger.error("sync failed: %s", e)
        return 1


# ============================================================================
# --loop 模式：拉模型（Phase 2 行为，长期运行）
# ============================================================================
async def run_loop(
    collector: ScannerCollector,
    client: MiniSOCClient,
    scanner_id: str,
    heartbeat_interval: int = 30,
    poll_interval: int = 10,
) -> int:
    """拉模型主循环：每30s 心跳 + 每10s 拉任务 + 跑 nmap + 推数据 + 回写状态。

    循环结构（final.md §7.4）：
      while True:
        1. heartbeat(scanner_id, capabilities, running_tasks)   # L1
        2. fetch_pending(scanner_id, caps)                      # 拉任务
        3. for each pending: claim → run nmap → sync data → report_status
        4. sleep(poll_interval)
    """
    # 扫描器能力（心跳上报 + 拉任务过滤）。env SCANNER_CAPS 可覆盖（逗号分隔）。
    caps = [c.strip() for c in os.getenv("SCANNER_CAPS", "public,internal,ports").split(",") if c.strip()]
    logger.info(
        "=== scanner-collector --loop 启动 (scanner_id=%s hb=%ds poll=%ds caps=%s) ===",
        scanner_id, heartbeat_interval, poll_interval, caps,
    )

    current_running = 0
    last_heartbeat = 0.0
    import time

    while True:
        try:
            # 1. 心跳（30s 一次，懒判断）
            now = time.monotonic()
            if now - last_heartbeat >= heartbeat_interval:
                try:
                    await client.heartbeat(
                        scanner_id=scanner_id,
                        capabilities=caps,
                        running_tasks=current_running,
                    )
                    last_heartbeat = now
                except Exception as e:
                    logger.warning("heartbeat 失败（继续运行）: %s", e)

            # 2. 拉任务
            tasks = await client.fetch_pending(scanner_id, caps=caps)
            if tasks:
                logger.info("拉到 %d 个待认领任务", len(tasks))

            # 3. 逐个认领 → 跑 nmap → 推数据 → 回写
            for task in tasks:
                task_uuid = task["task_uuid"]
                logger.info("尝试认领 task %s (mode=%s)", task_uuid[:8], task.get("mode"))

                # 3.1 claim
                try:
                    claim_resp = await client.claim(task_uuid, scanner_id)
                except Exception as e:
                    logger.warning("claim task %s 失败: %s", task_uuid[:8], e)
                    continue
                if not claim_resp.get("claimed", False):
                    logger.info("task %s 已被别的 scanner 认领", task_uuid[:8])
                    continue

                current_running += 1
                logger.info("认领成功 task %s，开始 nmap 扫描", task_uuid[:8])

                # 3.2 跑 nmap（按任务 mode 路由：internal=discovery，public/ports=port）
                try:
                    items, counts, data_type = await _run_nmap_for_task(
                        collector, task,
                    )
                    # discovery findings 落扫描器来源（run_loop 有 scanner_id）
                    if data_type == "discovery":
                        for it in items:
                            it.setdefault("scanner_id", scanner_id)
                except Exception as e:
                    logger.exception("nmap 扫描异常 task %s", task_uuid[:8])
                    try:
                        await client.report_status(
                            task_uuid=task_uuid, status="failed",
                            error_message=f"nmap exception: {e}",
                        )
                    except Exception:
                        pass
                    current_running = max(0, current_running - 1)
                    continue

                # 3.3 推数据（discovery → data_type=discovery 写 findings；port → asset_ports）
                sync_source = "scanner" if data_type == "discovery" else "scanner-port"
                try:
                    sync_resp = await client.sync(
                        source=sync_source,
                        data_type=data_type,
                        items=items,
                        metadata={"scan_task_uuid": task_uuid},
                    )
                    # sync() 已解包 envelope，返回的就是 data：{total,created,updated,...}
                    # 用控制面返回的真实 created/updated 覆盖（避免 local 估错）
                    if isinstance(sync_resp, dict):
                        if sync_resp.get("created") is not None:
                            counts["items_created"] = sync_resp.get("created", 0)
                        if sync_resp.get("updated") is not None:
                            counts["items_updated"] = sync_resp.get("updated", 0)
                except Exception as e:
                    logger.error("推数据失败 task %s: %s", task_uuid[:8], e)
                    counts["items_failed"] = counts.get("items_scanned", len(items))

                # 3.4 回写结果
                try:
                    await client.report_status(
                        task_uuid=task_uuid,
                        status="success" if not counts.get("items_failed") else "failed",
                        scanner_id=scanner_id,
                        items_scanned=counts.get("items_scanned", len(items)),
                        items_created=counts.get("items_created", 0),
                        items_updated=counts.get("items_updated", 0),
                        items_failed=counts.get("items_failed", 0),
                        duration_ms=counts.get("duration_ms", 0),
                    )
                except Exception as e:
                    logger.warning("report_status 失败 task %s: %s", task_uuid[:8], e)
                finally:
                    current_running = max(0, current_running - 1)

            # 4. sleep
            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            logger.info("scanner-collector --loop cancelled by signal")
            break
        except Exception as e:
            logger.exception("scanner-collector --loop tick 异常")
            await asyncio.sleep(poll_interval)   # 防爆栈

    return 0


async def _run_nmap_for_task(collector: ScannerCollector, task: dict) -> tuple[list, dict, str]:
    """跑一个 task 的 nmap，返回 (items, counts, data_type)。

    按任务 mode 路由（不再忽略任务）：
      - internal → collector.collect_for_task → nmap -sn 主机发现 → data_type=discovery
      - public/ports → nmap -sV 端口扫描 → data_type=port
    目标从 task.target_summary 取。
    """
    import time
    t0 = time.monotonic()
    result = await collector.collect_for_task(task)
    duration_ms = int((time.monotonic() - t0) * 1000)
    items = result.items
    data_type = result.data_type.value  # DataType enum → "discovery" / "port"
    counts = {
        "items_scanned": len(items),
        "items_created": len(items),
        "items_updated": 0,
        "items_failed": len(result.metadata.get("failed_targets", []) or []),
        "duration_ms": duration_ms,
    }
    return items, counts, data_type


# ============================================================================
# CLI 入口
# ============================================================================
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="scanner-collector: 公网暴露面扫描")
    p.add_argument("--once", action="store_true", default=True,
                   help="单次扫描后退出（默认；Phase 1 行为）")
    p.add_argument("--loop", action="store_true",
                   help="拉模型循环模式（Phase 2 行为；需 SCANNER_ID env）")
    p.add_argument("--scanner-id", default=os.getenv("SCANNER_ID"),
                   help="扫描器 ID（控制面注册时分配；--loop 必填）")
    p.add_argument("--nmap-binary", default=os.getenv("NMAP_BINARY", "/usr/bin/nmap"))
    p.add_argument("--nmap-timeout", type=int, default=int(os.getenv("NMAP_TIMEOUT", "300")))
    p.add_argument("--max-rate", type=int, default=int(os.getenv("NMAP_MAX_RATE", "100")))
    p.add_argument("--heartbeat-interval", type=int,
                   default=int(os.getenv("HEARTBEAT_INTERVAL", "30")))
    p.add_argument("--poll-interval", type=int,
                   default=int(os.getenv("POLL_INTERVAL", "10")))
    return p.parse_args()


async def main() -> int:
    args = parse_args()

    minisoc_url = os.getenv("MINISOC_URL", "http://host.docker.internal:8000")
    api_key = os.getenv("MINISOC_API_KEY") or os.getenv("SCANNER_API_KEY")
    if not api_key:
        logger.error("MINISOC_API_KEY or SCANNER_API_KEY env not set")
        return 1

    client = MiniSOCClient(
        base_url=minisoc_url,
        api_key=api_key,
        timeout=int(os.getenv("MINISOC_TIMEOUT", "30")),
    )
    if not await client.health_check():
        logger.error("AI-miniSOC not reachable at %s", minisoc_url)
        return 1

    collector = ScannerCollector(
        nmap_binary=args.nmap_binary,
        nmap_timeout=args.nmap_timeout,
        max_rate=args.max_rate,
    )
    if not await collector.test_connection():
        logger.error("nmap unavailable or no targets configured")
        return 1

    if args.loop:
        if not args.scanner_id:
            logger.error("--loop 需要 --scanner-id 或 SCANNER_ID env")
            return 1
        return await run_loop(
            collector, client,
            scanner_id=args.scanner_id,
            heartbeat_interval=args.heartbeat_interval,
            poll_interval=args.poll_interval,
        )
    return await run_once(collector, client)


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
        sys.exit(rc)
    except KeyboardInterrupt:
        logger.info("interrupted by user")
        sys.exit(130)