"""存在性结算调度器（P1/P2/P3）

每 15 分钟结算一次未处理的扫描覆盖凭证（缺席计次 + lifecycle 迁移）。
同步 DB 工作全部在线程里做（§4.5 教训：同步函数绝不占 event loop），
线程内自建 Session，try commit / except rollback / finally close。
"""

import asyncio
import logging
import threading

from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 15 * 60
_lock = threading.Lock()
_task: asyncio.Task | None = None


def _run_settle_once() -> None:
    from app.services.asset_presence import settle_coverage, _maybe_alert_scan_failures

    with SessionLocal() as session:
        try:
            settle_coverage(session)
            _maybe_alert_scan_failures(session)
        except Exception:
            session.rollback()
            logger.exception("presence settle round failed")
        finally:
            session.close()


async def _loop() -> None:
    # 启动先等 5 分钟再第一轮（等服务/采集器热起来）
    await asyncio.sleep(300)
    while True:
        # threading.Lock 串行化（防 POST /graph/rebuild 式并发重入）
        if _lock.acquire(blocking=False):
            try:
                await asyncio.to_thread(_run_settle_once)
            finally:
                _lock.release()
        else:
            logger.debug("presence settle already running, skipped")
        await asyncio.sleep(INTERVAL_SECONDS)


def start_presence_scheduler() -> None:
    global _task
    if _task is not None:
        return
    _task = asyncio.create_task(_loop(), name="presence-settle")
    logger.info("presence scheduler started (interval=%ds)", INTERVAL_SECONDS)


async def stop_presence_scheduler() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    logger.info("presence scheduler stopped")
