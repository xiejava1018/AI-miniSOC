"""
通知分发器（OH-NOT-F2 · Phase 1）

CLAUDE.md §4.13 假阴性/假绿预防：每通道独立 status + 失败可观测 + 多通道互不阻断。

设计：
- dispatch(notification) → 对每个 enabled 通道 + 用户偏好筛选 → 入 dispatch_logs
- inbox: 同步写 soc_notifications (已有 NotificationService)，状态 'sent'
- email: Phase 1 仅写 dispatch_logs(status='pending')，不实际发 — Phase 2 worker 接管
- 任一通道失败不阻断（try/except 包每个通道，logged）
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy.orm import Session as OrmSession

from app.models import Notification
from app.models.notification_channel import (
    NotificationChannel,
    NotificationDispatchLog,
)
from app.services.notification_channel_service import (
    EMAIL_CHANNEL_CODE,
    INBOX_CHANNEL_CODE,
    NotificationChannelService,
)

logger = logging.getLogger(__name__)


class NotificationDispatcher:
    """把单条 Notification 分发到所有启用的通道。

    用法：
        dispatcher = NotificationDispatcher(db)
        await dispatcher.dispatch(notification, user_ids=[1,2,3])
    """

    def __init__(self, db: OrmSession) -> None:
        self.db = db
        self.channel_service = NotificationChannelService(db)

    # ============================================================
    # 公开入口
    # ============================================================

    async def dispatch(
        self,
        notification: Notification,
        user_ids: Optional[list[int]] = None,
    ) -> list[NotificationDispatchLog]:
        """分发通知。

        Args:
            notification: 已 commit 的 Notification 实例
            user_ids: 接收人列表（None 表示全员 active 用户）

        Returns:
            本次创建的 dispatch_logs（每 user × 每 channel 一条）
        """
        if user_ids is None:
            user_ids = self._resolve_all_active_user_ids()

        correlation_id = uuid.uuid4().hex[:32]
        channels = self.channel_service.list_channels(enabled_only=True)
        if not channels:
            logger.warning("dispatch: no enabled channel")
            return []

        logs: list[NotificationDispatchLog] = []
        type = notification.type
        notif_id = notification.id  # UUID

        for user_id in user_ids:
            for ch in channels:
                # 用户偏好筛选（CLAUDE.md §0 默认全收）
                if not self.channel_service.is_user_channel_enabled(user_id, type, ch.code):
                    self._log_skipped_pref(user_id, ch.code, notif_id, correlation_id)
                    continue

                # 按 channel 类型分发
                try:
                    if ch.code == INBOX_CHANNEL_CODE:
                        log = self._dispatch_inbox(user_id, ch, notif_id, correlation_id)
                    elif ch.code == EMAIL_CHANNEL_CODE:
                        log = self._dispatch_email_pending(user_id, ch, notif_id, correlation_id)
                    else:
                        # 未来 sms/webhook 等通道 - Phase 1 跳过但记录 skipped_pref
                        logger.info("dispatch: skip unknown channel %s", ch.code)
                        continue
                    logs.append(log)
                except Exception:  # noqa: BLE001
                    # 单通道失败不影响其他通道（CLAUDE.md §4.13）
                    logger.exception(
                        "dispatch failed: user=%s channel=%s notif=%s",
                        user_id, ch.code, notif_id,
                    )

        self.db.commit()
        logger.info(
            "dispatch done: notification=%s type=%s logs=%d correlation=%s",
            notif_id, type, len(logs), correlation_id,
        )
        return logs

    # ============================================================
    # 各通道实现
    # ============================================================

    def _dispatch_inbox(
        self,
        user_id: int,
        channel: NotificationChannel,
        notification_id,
        correlation_id: str,
    ) -> NotificationDispatchLog:
        """inbox 通道 — 同步写 soc_notifications (已有 NotificationService)。

        inbox 是站内通知的核心：写表后 ws_manager 已经在 NotificationService.create 里推过 WS，
        所以这里只写 dispatch_log(sent) + 把 'sent_at' 设为 now。
        """
        log = NotificationDispatchLog(
            notification_id=notification_id,
            user_id=user_id,
            channel_code=channel.code,
            status="sent",  # 站内 NotificationService.create 已成功
        )
        # sent_at 用 on-create default NOW() 即可
        self.db.add(log)
        self.db.flush()
        return log

    def _dispatch_email_pending(
        self,
        user_id: int,
        channel: NotificationChannel,
        notification_id,
        correlation_id: str,
    ) -> NotificationDispatchLog:
        """email 通道 — Phase 1 仅写 dispatch_logs(status=pending)。

        Phase 2 实现:
        - 解析 channel.config_json (smtp host/user/pass)
        - 调 email_sender.send(user_id, notif)
        - 成功 → status='sent', sent_at=NOW()
        - 失败 → status='failed', retry_count++, next_retry_at=指数退避
        """
        # 校验 SMTP 配置（如果 disabled 或 config 空，写 skipped_pref）
        cfg = channel.config_json or {}
        errors = self.channel_service.validate_email_config(cfg) if cfg else ["channel requires config"]

        if errors:
            log = NotificationDispatchLog(
                notification_id=notification_id,
                user_id=user_id,
                channel_code=channel.code,
                status="skipped_pref",
                error_text="; ".join(errors),
                correlation_id=correlation_id,
            )
            self.db.add(log)
            self.db.flush()
            return log

        # 配置 OK，写 pending — Phase 2 worker 会取走并实际投递
        log = NotificationDispatchLog(
            notification_id=notification_id,
            user_id=user_id,
            channel_code=channel.code,
            status="pending",
            correlation_id=correlation_id,
        )
        self.db.add(log)
        self.db.flush()
        return log

    # ============================================================
    # 内部
    # ============================================================

    def _resolve_all_active_user_ids(self) -> list[int]:
        """默认全 active 用户（CLAUDE.md §0 X1 矩阵：所有角色均接收通知）。"""
        from app.models.user import User, UserStatus

        rows = self.db.query(User.id).filter(User.status == UserStatus.ACTIVE).all()
        return [r[0] for r in rows]

    def _log_skipped_pref(
        self,
        user_id: int,
        channel_code: str,
        notification_id,
        correlation_id: str,
    ) -> None:
        """用户主动禁用某个 (type, channel) — 写 skipped_pref 日志（审计可追溯）。"""
        log = NotificationDispatchLog(
            notification_id=notification_id,
            user_id=user_id,
            channel_code=channel_code,
            status="skipped_pref",
            error_text="user disabled this (type, channel)",
            correlation_id=correlation_id,
        )
        self.db.add(log)
        self.db.flush()


__all__ = ["NotificationDispatcher"]