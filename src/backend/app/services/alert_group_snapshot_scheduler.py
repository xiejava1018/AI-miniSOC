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

from app.core.database import SessionLocal, engine
from app.models.base import Base
import app.models  # noqa: F401  确保模型注册（含 soc_alert_groups）
from app.services.alert_group_snapshot_service import (
    AlertGroupSnapshotService,
    RETENTION_DAYS,
)

logger = logging.getLogger(__name__)

_SNAPSHOT_TABLES = {"soc_alert_groups"}
INTERVAL_SECONDS = 6 * 3600  # 每 6 小时
_FIRST_RUN_DELAY = 60         # 启动后 60s 首次跑

_task = None


def _ensure_tables() -> None:
    tables = [t for n, t in Base.metadata.tables.items() if n in _SNAPSHOT_TABLES]
    Base.metadata.create_all(bind=engine, tables=tables)


async def run_snapshot_once(hours: int = 24) -> dict:
    """执行单轮快照（含保留期清理），返回统计。"""
    db = SessionLocal()
    try:
        svc = AlertGroupSnapshotService(db)
        stats = svc.snapshot(hours=hours)
        removed = svc.cleanup_retention()
        stats["retention_removed"] = removed
        logger.info("alert group snapshot done: %s", stats)
        return stats
    except Exception:
        logger.exception("alert group snapshot failed")
        return {"error": "exception"}
    finally:
        db.close()


async def _loop() -> None:
    logger.info("alert group snapshot loop started, interval=%ds", INTERVAL_SECONDS)
    _ensure_tables()
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
    _ensure_tables()
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
