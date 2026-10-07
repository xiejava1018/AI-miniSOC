"""
邮件投递 worker（OH-NOT-F2 · Phase 2）

CLAUDE.md §0/§4.7 异步任务 + §4.13 失败可观测。

设计：
- 60s tick 扫 soc_notification_dispatch_logs WHERE status='pending' AND channel_code='email'
- 取 retry 间隔（指数退避 60s / 300s / 1500s / 3600s / 7200s）
- max_retries (默认 3) → status='failed'
- 成功 → status='sent', sent_at=NOW()
- 部分 5xx 错误 retry / 4xx 不 retry
- watchdog 集成（CLAUDE.md §0 任务可观测性）
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session as OrmSession
from sqlalchemy import select

from app.core import database as _db
from app.models import User
from app.models.notification import Notification
from app.models.notification_channel import NotificationDispatchLog
from app.services.email_sender import render_and_send, EmailSendError
from app.services.notification_channel_service import NotificationChannelService

logger = logging.getLogger(__name__)

WORKER_TASK_KEY = "__email_notifier_worker__"
WORKER_INTERVAL_S = 60
WORKER_TIMEOUT_S = 120

# 反退避表：重试间隔（retry_count=1,2,3,...）
RETRY_BACKOFF_S = [60, 300, 1500, 3600, 7200]  # 1m, 5m, 25m, 1h, 2h
DEFAULT_MAX_RETRIES = 3

_worker_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _next_retry_at(retry_count: int) -> datetime:
    """根据 retry_count 算下次重试时间（CLAUDE.md §0 指数退避约定）。"""
    if retry_count >= len(RETRY_BACKOFF_S):
        backoff = RETRY_BACKOFF_S[-1]
    else:
        backoff = RETRY_BACKOFF_S[retry_count]
    return _now() + timedelta(seconds=backoff)


def _tick_once() -> dict:
    """一次 tick — 同步执行（worker 在线程里跑）。

    Returns: dict {scanned, sent, retry, failed, skipped}
    """
    db = _db.SessionLocal()
    stats = {"scanned": 0, "sent": 0, "retry": 0, "failed": 0, "skipped": 0}
    try:
        # 1. 查 pending + failed (需要重试) 的 email dispatch_logs
        now = _now()
        stmt = (
            select(NotificationDispatchLog)
            .where(
                NotificationDispatchLog.channel_code == "email",
                NotificationDispatchLog.status.in_(["pending", "failed"]),
            )
            .where(
                (NotificationDispatchLog.next_retry_at.is_(None))
                | (NotificationDispatchLog.next_retry_at <= now)
            )
            .order_by(NotificationDispatchLog.created_at)
            .limit(50)  # 单 tick 处理上限，避免阻塞
        )
        rows = list(db.execute(stmt).scalars())
        stats["scanned"] = len(rows)

        if not rows:
            return stats

        # 2. 加载 email 通道 + 校验
        channel_svc = NotificationChannelService(db)
        email_cfg = channel_svc.get_email_config(use_cache=False)
        if email_cfg is None:
            logger.warning("email worker: channel disabled or not configured")
            for row in rows:
                row.status = "skipped_pref"
                row.error_text = "email channel disabled or unconfigured"
            db.commit()
            stats["skipped"] = len(rows)
            return stats

        # 3. 逐条处理
        # 把 user 一次批量预加载，避免 N+1
        user_ids = {r.user_id for r in rows}
        users = {u.id: u for u in db.query(User).filter(User.id.in_(user_ids)).all()}

        for row in rows:
            user = users.get(row.user_id)
            if user is None:
                row.status = "failed"
                row.error_text = f"user {row.user_id} not found"
                stats["failed"] += 1
                continue

            if not user.email:
                row.status = "skipped_pref"
                row.error_text = f"user {row.user_id} has no email"
                stats["skipped"] += 1
                continue

            # 找关联的 Notification
            notif: Optional[Notification] = None
            if row.notification_id:
                notif = db.query(Notification).filter(Notification.id == row.notification_id).first()
            if notif is None:
                row.status = "failed"
                row.error_text = "notification not found"
                stats["failed"] += 1
                continue

            # 实际投递 (Phase 2: 异步)
            try:
                # render_and_send 是 async — 同步 wrapper 用 asyncio.run
                # 注意: 在线程里跑 asyncio.run 会创建新 event loop
                extra_ctx = _extract_extra_context(notif)
                result = asyncio.run(
                    render_and_send(
                        email_cfg,
                        user=user,
                        notification=notif,
                        type=notif.type or "_default",
                        extra_context=extra_ctx,
                    )
                )
                # 成功
                row.status = "sent"
                row.sent_at = _now()
                row.error_text = None
                row.retry_count = (row.retry_count or 0)
                stats["sent"] += 1
                logger.info(
                    "email sent via worker: log_id=%s user=%s to=%s elapsed=%dms",
                    row.id, user.id, user.email, result.get("elapsed_ms", 0),
                )
            except EmailSendError as e:
                row.retry_count = (row.retry_count or 0) + 1
                row.error_text = str(e)[:1000]
                max_retries = email_cfg.get("max_retries", DEFAULT_MAX_RETRIES)
                if row.retry_count >= max_retries:
                    row.status = "failed"
                    stats["failed"] += 1
                    logger.warning(
                        "email failed (max retries %d): log_id=%s err=%s",
                        max_retries, row.id, e,
                    )
                else:
                    # 重试（退避 + state 保持 failed 让 watchdog 知道）
                    row.status = "failed"  # 仍标 failed, 但 next_retry_at 排到了
                    row.next_retry_at = _next_retry_at(row.retry_count)
                    stats["retry"] += 1
                    logger.info(
                        "email retry scheduled: log_id=%s retry=%d next=%s",
                        row.id, row.retry_count, row.next_retry_at,
                    )
            except Exception as e:  # noqa: BLE001
                logger.exception("email unexpected error: log_id=%s", row.id)
                row.status = "failed"
                row.error_text = f"unexpected: {type(e).__name__}: {e}"[:1000]
                stats["failed"] += 1

        db.commit()
        return stats

    finally:
        db.close()


def _extract_extra_context(notif: Notification) -> dict:
    """为模板渲染准备 ctx。

    Phase 2 规则：
    1. 模板默认需要的通用 key 必须有 fallback（避免 KeyError）
    2. notif.content 如果是 JSON 格式则 merge 进 ctx（高级用）
    3. 其他 type 来自 worker.render_and_send 的 extra_context 参数
    """
    from datetime import datetime as _dt, timezone as _tz
    ctx: dict = {
        # 通用 fallback (模板必须有)
        "test_time": _dt.now(_tz.utc).isoformat(),
        # 默认空 dict, JSON content 会被 merge
    }
    if notif.content:
        try:
            parsed = json.loads(notif.content)
            if isinstance(parsed, dict):
                ctx.update(parsed)
        except (json.JSONDecodeError, TypeError):
            # content 不是 JSON — 当文本处理，无 extra ctx
            pass
    return ctx


async def _worker_loop() -> None:
    logger.info("email notifier worker started (interval=%ds)", WORKER_INTERVAL_S)

    # 启动后立即 tick 一次 (CLAUDE.md §4.10 后端冷启动防护)
    try:
        stats = await asyncio.to_thread(_tick_once)
        if stats["scanned"] > 0:
            logger.info("email worker initial tick: %s", stats)
    except Exception:
        logger.exception("email worker initial tick failed")

    while _stop_event is not None and not _stop_event.is_set():
        try:
            stats = await asyncio.to_thread(_tick_once)
            if stats["scanned"] > 0:
                logger.info("email worker tick: %s", stats)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("email worker tick failed")
        try:
            await asyncio.wait_for(_stop_event.wait(), timeout=WORKER_INTERVAL_S)
        except asyncio.TimeoutError:
            pass
    logger.info("email notifier worker stopped")


def start_email_notifier_worker() -> None:
    """启动 worker (CLAUDE.md §2.3 main.py lifespan 启动)"""
    global _worker_task, _stop_event
    if _worker_task is not None and not _worker_task.done():
        return
    _stop_event = asyncio.Event()
    _worker_task = asyncio.create_task(_worker_loop())
    logger.info("email notifier worker task created")


async def stop_email_notifier_worker() -> None:
    global _worker_task, _stop_event
    if _stop_event is not None:
        _stop_event.set()
    if _worker_task is not None:
        _worker_task.cancel()
        try:
            await _worker_task
        except (asyncio.CancelledError, Exception):
            pass
    _worker_task = None
    logger.info("email notifier worker stopped")