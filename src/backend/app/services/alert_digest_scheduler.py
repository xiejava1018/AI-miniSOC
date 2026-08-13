"""
告警治理摘要自动调度器（Phase 2）

在 FastAPI lifespan 中启动后台 asyncio task，每日定点（默认 08:00）生成一份
告警治理摘要（AlertDigestService.generate，含 AI 研判 + 通知推送）。
严格复用 alert_group_snapshot_scheduler / browsing_detection 范式：
- start_alert_digest_scheduler() : 启动（幂等，受 ALERT_DIGEST_SCHEDULER_ENABLED 控制）
- stop_alert_digest_scheduler()  : 停止
- run_digest_once(hours)         : 手动触发单轮（不依赖调度，便于验证）

注意：摘要内部已包含 AI 研判与通知推送，调度器只负责"定时触发"。
"""
import asyncio
import logging
from datetime import datetime, timedelta

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.alert_digest_service import AlertDigestService

logger = logging.getLogger(__name__)

_task = None
_FIRST_RUN_DELAY = 90  # 启动后稍等，避免与其他后台任务挤在同一时刻抢资源


def _seconds_until_next(hour: int) -> float:
    """计算现在到下一个目标整点(本地时区)的秒数；已过则推到明天。"""
    now = datetime.now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


async def run_digest_once(hours: int = 24) -> dict:
    """手动触发一轮摘要生成（返回统计；失败返回 {"error": ...}）。"""
    db = SessionLocal()
    try:
        svc = AlertDigestService(db)
        digest = await svc.generate(hours=hours)
        logger.info(
            "alert digest generated: id=%s total=%s ai_model=%s",
            digest.id, digest.total_alerts, digest.ai_model,
        )
        return {
            "digest_id": str(digest.id),
            "total_alerts": digest.total_alerts,
            "groups": len(digest.top_groups or []),
            "ai_model": digest.ai_model,
        }
    except Exception:
        logger.exception("alert digest generation failed")
        return {"error": "exception"}
    finally:
        db.close()


async def _loop() -> None:
    hour = settings.ALERT_DIGEST_SCHEDULER_HOUR
    logger.info("alert digest scheduler loop started, target daily @%02d:00", hour)
    await asyncio.sleep(_FIRST_RUN_DELAY)
    while True:
        try:
            delay = _seconds_until_next(hour)
            logger.info("alert digest scheduler: next run in %.0fs", delay)
            await asyncio.sleep(delay)
            await run_digest_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("digest loop iteration failed")
            await asyncio.sleep(3600)  # 出错后 1h 再试，避免空转


def start_alert_digest_scheduler() -> None:
    """启动后台摘要任务（幂等）"""
    global _task
    if not settings.ALERT_DIGEST_SCHEDULER_ENABLED:
        logger.info(
            "alert digest scheduler disabled by config (ALERT_DIGEST_SCHEDULER_ENABLED=False)"
        )
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("alert digest scheduler task started")


async def stop_alert_digest_scheduler() -> None:
    """停止后台摘要任务"""
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
    logger.info("alert digest scheduler task stopped")
