"""
lifespan 集成：启动对账 + 启动 watchdog + 启动通知 drain。

正确启动顺序（v0.4 P1-2）：
1. reconcile_on_startup：把残留 running run 标 unknown
2. upsert watchdog registry 行
3. 启动 notification drain task
4. 启动 watchdog loop
5. 业务 scheduler 在之后启动（main.py 里调）

停止顺序：
1. 业务 scheduler 先停
2. watchdog 停
3. drain 停（最后停，保证剩余通知发出去）
"""
from __future__ import annotations

import logging

from app.core import database as _db

from . import store
from .handlers import register_all_handlers_now
from .notification_queue import start_notification_drain, stop_notification_drain
from .watchdog import start_watchdog, stop_watchdog

logger = logging.getLogger(__name__)


async def bootstrap_task_observability() -> dict:
    """在 FastAPI lifespan 早期调用。返回对账统计。"""
    db = _db.SessionLocal()
    try:
        stats = store.reconcile_on_startup(db)
    finally:
        db.close()
    # 预注册所有 @track_task handler（不执行 body）
    registered = register_all_handlers_now()
    stats["handlers_registered"] = registered
    # 通知队列先启动（让 watchdog 能入通知）
    await start_notification_drain()
    # 看门狗启动
    start_watchdog()
    logger.info("task observability bootstrapped: %s", stats)
    return stats


async def shutdown_task_observability() -> None:
    """在 FastAPI lifespan 关闭时调用。"""
    await stop_watchdog()
    await stop_notification_drain()
    logger.info("task observability shut down")
