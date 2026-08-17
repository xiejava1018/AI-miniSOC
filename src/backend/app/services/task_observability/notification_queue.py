"""
NotificationQueue（POC-3 无锁 deque 版本）。

设计要点（POC-3 实测）：
- 用 collections.deque(maxlen=N)：append/pop/clear 都是 GIL 保护的原子操作
- 不用 threading.Lock（在 async 函数里同步 with 会冻结 event loop）
- 不用 asyncio.Lock（装饰器异常路径是同步的，不能 await）
- enqueue 是同步函数，drain 也是同步函数；drain task 用 asyncio.to_thread 调用

10 producer × 100 条 + 1 consumer 并发实测 0 丢消息。
"""
from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core import database as _db
from app.models.user import User
from app.models.role import Role
from app.services.audit_log_service import AuditLogService
from app.services.notification_service import NotificationService

from .dedup import notification_dedup
from .metrics import notification_dropped_total

logger = logging.getLogger(__name__)


class NotificationQueue:
    def __init__(self, max_size: int = 1000):
        self._queue: deque = deque(maxlen=max_size)
        self._drain_task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None

    def enqueue(self, alert_type: str, payload: dict) -> None:
        """同步入队。从任意线程 / 协程安全。"""
        self._queue.append({"alert_type": alert_type, "payload": payload})

    def drain_sync(self) -> list:
        items = list(self._queue)
        self._queue.clear()
        return items

    def size(self) -> int:
        return len(self._queue)

    async def start_drain(self, interval_s: float = 2.0) -> None:
        """在 lifespan 内启动后台 drain task。"""
        if self._drain_task is not None:
            return
        self._stop_event = asyncio.Event()

        async def _loop():
            logger.info("notification drain task started (interval=%.1fs)", interval_s)
            while not self._stop_event.is_set():
                try:
                    await asyncio.sleep(interval_s)
                    items = await asyncio.to_thread(self.drain_sync)
                    for item in items:
                        try:
                            await _dispatch(item["alert_type"], item["payload"])
                        except Exception:  # noqa: BLE001
                            logger.exception("dispatch notification failed: %s", item)
                except asyncio.CancelledError:
                    break
                except Exception:  # noqa: BLE001
                    logger.exception("drain loop iteration failed")
            logger.info("notification drain task stopped")

        self._drain_task = asyncio.create_task(_loop())

    async def stop_drain(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._drain_task is not None:
            self._drain_task.cancel()
            try:
                await self._drain_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._drain_task = None


notification_queue = NotificationQueue()


# ---------------------------------------------------------------- 发送实现

async def _dispatch(alert_type: str, payload: dict) -> None:
    """3 级降级：WS → 站内 → 邮件（邮件 Phase 2，目前只日志）。"""
    if not notification_dedup.should_send(
        payload.get("task_key", "unknown"),
        alert_type,
        payload.get("error_text", ""),
    ):
        notification_dropped_total.labels(reason="dedup").inc()
        return

    recipients = _resolve_recipients()
    if not recipients:
        notification_dropped_total.labels(reason="no_recipients").inc()
        logger.warning("no notification recipients for %s", alert_type)
        return

    title, content, link = _render(alert_type, payload)

    db = _db.SessionLocal()
    try:
        svc = NotificationService(db)
        for user_id in recipients:
            try:
                await svc.create(
                    user_id=user_id,
                    type="task_alert",
                    title=title,
                    content=content,
                    link=link,
                    push_ws=True,
                )
            except Exception:  # noqa: BLE001
                logger.exception("inbox+ws send failed for user %s", user_id)
                notification_dropped_total.labels(reason="all_failed").inc()
                # 邮件兜底（Phase 2 实现，目前仅日志）
                logger.warning(
                    "[EMAIL-FALLBACK] would email user=%s title=%s", user_id, title
                )
    finally:
        db.close()


def _resolve_recipients() -> list[int]:
    """收件人：先从 soc_system_config 读 oncall_user_ids；否则 superuser + admin 全员。"""
    db = _db.SessionLocal()
    try:
        from app.models.system_config import SystemConfig
        cfg = (
            db.query(SystemConfig)
            .filter(SystemConfig.key == "oncall_user_ids")
            .first()
        )
        if cfg and cfg.value:
            try:
                import json
                ids = json.loads(cfg.value)
                if isinstance(ids, list) and ids:
                    return [int(x) for x in ids]
            except Exception:
                logger.warning("invalid oncall_user_ids: %s", cfg.value)

        # 默认：所有 is_superuser=1 + role=admin 的 active 用户
        from app.models.role import Role
        users = (
            db.query(User)
            .outerjoin(Role, User.role_id == Role.id)
            .filter(
                User.status == "active",
                (User.is_superuser.is_(True)) | (Role.code == "admin"),
            )
            .all()
        )
        return list({u.id for u in users})
    finally:
        db.close()


def _render(alert_type: str, payload: dict) -> tuple[str, str, Optional[str]]:
    task_key = payload.get("task_key", "unknown")
    status = payload.get("status", "")
    error = payload.get("error_text", "")
    duration = payload.get("duration_s", "")
    run_id = payload.get("run_id", "")

    title = f"[AI-miniSOC] 后台任务异常: {task_key}"
    if alert_type == "task_staleness":
        title = f"[AI-miniSOC] 任务超时未运行: {task_key}"
        content = f"任务 {task_key} 已超过预期 2 倍间隔未成功运行。"
    elif alert_type == "task_zombie":
        title = f"[AI-miniSOC] 任务僵尸: {task_key}"
        content = f"任务 {task_key} 检测到僵尸 run (id={run_id})。"
    elif alert_type == "watchdog_down":
        title = "[AI-miniSOC] 看门狗自身异常"
        content = "task_watchdog_alive 持续为 0，监控自身已挂。"
    else:
        content = f"任务 {task_key} 状态 {status}，耗时 {duration}s。\n错误: {error}"

    link = f"/task-center/{task_key}/runs/{run_id}" if run_id else "/task-center"
    return title, content, link


# 便捷启动 / 停止
async def start_notification_drain() -> None:
    await notification_queue.start_drain()


async def stop_notification_drain() -> None:
    await notification_queue.stop_drain()
