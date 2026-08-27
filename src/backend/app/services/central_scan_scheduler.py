"""
中央扫描调度器（P3/F-S3 控制面调度，final.md §8.2）

调度模式（v1.3 F-1）：与现有 alert_digest_scheduler / cisa_kev_scheduler 一致
——固定秒数间隔，不引入 cron 字符串解析。

任务模式：
  - internal 每天 03:00 UTC
  - public   每天 04:00 UTC
  - 启动后先 sleep 到下一个目标时刻（避免启动立即触发）
  - 出错后 1h 再试（与 alert_digest_scheduler.py:87 同款）
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)


# ============================================================================
# 配置（final.md §8.2）
# ============================================================================
INTERVAL_SECONDS = 24 * 3600  # 每天一次
EXEC_HOURS = {
    "internal": 3,    # 每天 03:00 UTC
    "public":   4,    # 每天 04:00 UTC
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _seconds_until_next_exec(hour_24: int) -> int:
    """到下一个 hour_24 点的秒数（≥60s，避免启动后立即触发）。"""
    now = _utcnow()
    target = now.replace(hour=hour_24, minute=0, second=0, microsecond=0)
    if target <= now or (target - now).total_seconds() < 60:
        target += timedelta(days=1)
    return int((target - now).total_seconds())


def _resolve_targets(mode: str) -> list[dict]:
    """解析扫描目标（从 soc_scan_targets 表）。

    Phase 2 简化：
      - internal 模式：取 soc_scan_targets 中 scope='internal' 且 enabled=true
      - public   模式：取 soc_scan_targets 中 scope='public'   且 enabled=true
        + soc_assets 中 public_ip 非空的所有公网 IP（自动汇总）
        注意：不使用 asset_ip——云上资产的 asset_ip 是内网 IP（如 ECS 172.18.x），
        拿去公网扫描会扫不到真实暴露面
    """
    from app.models.scanner_models import ScanTarget
    from app.models.asset import Asset

    items: list[dict] = []
    with SessionLocal() as session:
        try:
            targets = (
                session.query(ScanTarget)
                .filter(ScanTarget.scope == mode, ScanTarget.enabled == True)  # noqa: E712
                .all()
            )
            for t in targets:
                items.append({
                    "type": "cidr" if mode == "internal" else "ip",
                    "value": t.value,
                    "source": "soc_scan_targets",
                })
            if mode == "public":
                # 自动汇总台账中登记了公网 IP 的资产（public_ip 字段）。
                # 不再用 exposure_level+asset_ip：那个组合会把内网 IP 当公网目标
                public_assets = (
                    session.query(Asset)
                    .filter(Asset.public_ip.isnot(None), Asset.public_ip != "")
                    .all()
                )
                for a in public_assets:
                    items.append({
                        "type": "ip",
                        "value": a.public_ip.strip(),
                        "source": f"soc_assets:{a.id}",
                    })
        except Exception as e:
            logger.warning("resolve_targets(%s) failed: %s", mode, e)
    return items


def _create_scan_task(mode: str, scope: str, target_summary: list, run_reason: str):
    """建一条 ScannerTask pending 任务（独立 session 防 rollback）。"""
    import uuid
    from app.models.scanner_models import ScannerTask

    with SessionLocal() as session:
        try:
            task = ScannerTask(
                task_uuid=uuid.uuid4(),
                mode=mode,
                scope=scope,
                status="pending",
                triggered_by="central_scan_scheduler",
                target_summary=target_summary,
                capabilities=[mode],
                run_reason=run_reason,
                assign_mode="auto",
            )
            session.add(task)
            session.commit()
            logger.info(
                "central_scan_scheduler 建任务 mode=%s scope=%s run_reason=%s task_uuid=%s targets=%d",
                mode, scope, run_reason, task.task_uuid, len(target_summary),
            )
            return task.task_uuid
        except Exception:
            session.rollback()
            raise


async def _mode_loop(mode: str, hour_24: int) -> None:
    """每个 mode 一个独立 loop。"""
    delay = _seconds_until_next_exec(hour_24)
    logger.info(
        "central_scan[%s] first run in %ds (at %02d:00 UTC)",
        mode, delay, hour_24,
    )
    await asyncio.sleep(delay)
    while True:
        try:
            target_summary = _resolve_targets(mode)
            if not target_summary:
                logger.info("central_scan[%s] 无目标，跳过", mode)
            else:
                _create_scan_task(
                    mode=mode, scope="scheduled",
                    target_summary=target_summary,
                    run_reason="scheduled",
                )
        except Exception:
            logger.exception("central_scan[%s] tick failed", mode)
            await asyncio.sleep(3600)   # 出错后 1h 再试（与 alert_digest_scheduler.py:87 同款）
            continue
        await asyncio.sleep(INTERVAL_SECONDS)


async def _loop() -> None:
    """主 loop 启每 mode 的子 loop（fire-and-forget asyncio.create_task）。"""
    logger.info("central_scan_scheduler started")
    # 主 loop 实际空转；每个 mode_loop 独立 tick
    while True:
        await asyncio.sleep(3600)


_loop_tasks: list[asyncio.Task] = []
_main_task: asyncio.Task | None = None


def start_central_scan_scheduler() -> None:
    """lifespan startup 注册。"""
    global _main_task
    if _main_task is not None:
        return
    for mode, hour in EXEC_HOURS.items():
        _loop_tasks.append(asyncio.create_task(_mode_loop(mode, hour), name=f"central_scan-{mode}"))
    _main_task = asyncio.create_task(_loop(), name="central_scan-main")
    logger.info("central_scan_scheduler: %d mode loops started", len(_loop_tasks))


async def stop_central_scan_scheduler() -> None:
    """lifespan shutdown 取消所有 loop。"""
    global _main_task
    for t in _loop_tasks:
        t.cancel()
    for t in _loop_tasks:
        try:
            await t
        except asyncio.CancelledError:
            pass
    if _main_task is not None:
        _main_task.cancel()
        try:
            await _main_task
        except asyncio.CancelledError:
            pass
        _main_task = None
    _loop_tasks.clear()
    logger.info("central_scan_scheduler stopped")