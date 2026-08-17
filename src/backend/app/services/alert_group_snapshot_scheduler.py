"""
告警簇快照调度器（方案 B）

在 FastAPI lifespan 中启动后台 asyncio task，每 6 小时对告警簇做一次全量快照，
写入 soc_alert_groups（支撑历史/趋势）。严格复用 browsing_detection/scheduler 的范式：
- start_alert_group_snapshot() : 启动（幂等）
- stop_alert_group_snapshot()  : 停止
- run_snapshot_once()         : 执行单轮（可手动触发）
"""
import asyncio
import logging

from app.core.database import SessionLocal
import app.models  # noqa: F401  确保模型注册（含 soc_alert_groups）
from app.services.alert_group_snapshot_service import (
    AlertGroupSnapshotService,
    RETENTION_DAYS,
)
from app.services.task_observability import track_task

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 6 * 3600  # 每 6 小时
_FIRST_RUN_DELAY = 60         # 启动后 60s 首次跑

_task = None

# P1-T2：原 _ensure_tables() 已迁移化（迁移 d1e2f3a4b5c6 / e2f3a4b5c6d7 创建
# soc_alert_groups / soc_alert_group_analyses）。生产启动路径不再有 create_all。


@track_task(
    task_key="alert_group_snapshot",
    task_name="告警簇快照",
    task_type="scheduled",
    schedule_expr="@every 6h",
    expected_interval_s=6 * 3600,
    timeout_s=1800,
)
async def run_snapshot_once(hours: int = 24) -> dict:
    """执行单轮快照（含保留期清理），返回统计。"""
    from app.services.task_observability import update_progress_stage
    db = SessionLocal()
    try:
        update_progress_stage("snapshot", processed=0, total=2)
        svc = AlertGroupSnapshotService(db)
        stats = svc.snapshot(hours=hours)
        update_progress_stage(
            "cleanup", processed=1, total=2,
            extra={"groups": stats.get("groups", 0)},
        )
        removed = svc.cleanup_retention()
        stats["retention_removed"] = removed
        update_progress_stage("done", processed=2, total=2, extra=stats)
        logger.info("alert group snapshot done: %s", stats)
        return stats
    except Exception:
        logger.exception("alert group snapshot failed")
        return {"error": "exception"}
    finally:
        db.close()


async def _loop() -> None:
    logger.info("alert group snapshot loop started, interval=%ds", INTERVAL_SECONDS)
    # P1-T2：原 _ensure_tables() 已移除，表由迁移 d1e2f3a4b5c6 / e2f3a4b5c6d7 保障
    await asyncio.sleep(_FIRST_RUN_DELAY)
    while True:
        try:
            await run_snapshot_once()
        except Exception:
            logger.exception("snapshot loop iteration failed")
        await asyncio.sleep(INTERVAL_SECONDS)


def start_alert_group_snapshot() -> None:
    """启动后台快照任务（幂等）"""
    global _task
    if _task is not None and not _task.done():
        return
    # P1-T2：原 _ensure_tables() 已移除，表由迁移 d1e2f3a4b5c6 / e2f3a4b5c6d7 保障
    _task = asyncio.create_task(_loop())
    logger.info("alert group snapshot task started")


async def stop_alert_group_snapshot() -> None:
    """停止后台快照任务"""
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
    logger.info("alert group snapshot task stopped")
