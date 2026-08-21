"""
主动推送调度器（PRD F4.2）

严格复用 alert_digest_scheduler / browsing_detection 范式：
- start_push_scheduler() : 启动（幂等，受 PUSH_SCHEDULER_ENABLED 控制）
- stop_push_scheduler()  : 停止
- run_push_once()        : 手动触发单轮（不依赖调度，供 API/测试/验证）

巡检周期默认 30 分钟（PUSH_SCHEDULER_INTERVAL_MINUTES）。
场景见 push_notification_service 模块注释。
"""
import asyncio
import logging

from app.core.config import settings
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

_task = None
_FIRST_RUN_DELAY = 120  # 启动后稍等，避免与其他后台任务挤在同一时刻


async def run_push_once() -> dict:
    """执行一轮巡检推送（返回各场景发送人数统计）。"""
    from app.services.push_notification_service import PushNotificationService
    db = SessionLocal()
    try:
        svc = PushNotificationService(db)
        result = await svc.run_all()
        if any(result.values()):
            logger.info("push scheduler round: %s", result)
        return result
    finally:
        db.close()


async def _loop() -> None:
    interval = max(int(settings.PUSH_SCHEDULER_INTERVAL_MINUTES), 5) * 60
    logger.info("push scheduler loop started, interval=%ds", interval)
    await asyncio.sleep(_FIRST_RUN_DELAY)
    while True:
        try:
            await run_push_once()
        except Exception:  # noqa: BLE001
            logger.exception("push scheduler round failed")
        await asyncio.sleep(interval)


def start_push_scheduler() -> None:
    global _task
    if not settings.PUSH_SCHEDULER_ENABLED:
        logger.info("push scheduler disabled by config")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop())


def stop_push_scheduler() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
        logger.info("push scheduler stopped")
