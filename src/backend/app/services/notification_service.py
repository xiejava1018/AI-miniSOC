"""
通知服务

封装 Notification 模型的 CRUD + WebSocket 推送。
所有外部触发源（手动测试 / AI 完成 / 严重告警）都应通过 `create()` 走单一入口。
"""

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Notification
from app.services.ws_manager import ws_manager

logger = logging.getLogger(__name__)


class NotificationService:
    """通知业务封装"""

    def __init__(self, db: Session) -> None:
        self.db = db

    # ============== 创建 ==============

    async def create(
        self,
        user_id: int,
        type: str,
        title: str,
        content: Optional[str] = None,
        link: Optional[str] = None,
        push_ws: bool = True,
    ) -> Notification:
        """入库并（可选）通过 WS 实时推送给目标用户。

        Phase 1 (OH-NOT-F2)：本方法保留原语义（仅单用户 inbox），调用方不受影响。
        需多用户 + 多通道分发走 `create_multi()`。
        """
        notif = Notification(
            user_id=user_id,
            type=type,
            title=title,
            content=content,
            link=link,
        )
        self.db.add(notif)
        self.db.commit()
        self.db.refresh(notif)

        if push_ws:
            await ws_manager.send_to_user(
                user_id,
                {
                    "type": "notification",
                    "data": {
                        "id": str(notif.id),
                        "user_id": notif.user_id,
                        "type": notif.type,
                        "title": notif.title,
                        "content": notif.content,
                        "link": notif.link,
                        "is_read": notif.is_read,
                        "created_at": notif.created_at.isoformat() if notif.created_at else None,
                    },
                },
            )
        return notif

    async def create_multi(
        self,
        user_ids: list[int],
        type: str,
        title: str,
        content: Optional[str] = None,
        link: Optional[str] = None,
        push_ws: bool = True,
    ) -> list[Notification]:
        """Phase 1 (OH-NOT-F2)：多用户 + 多通道分发。

        入库 1 条 soc_notifications (user_id=第一个用户)，然后调
        NotificationDispatcher 给所有 user_ids × 所有 enabled channels 写 dispatch_logs。

        Returns: 创建的 Notification 列表（每个 user_id 一条）
        """
        from .notification_dispatcher import NotificationDispatcher

        if not user_ids:
            return []

        notifications: list[Notification] = []
        first_id: Optional[object] = None
        for uid in user_ids:
            notif = Notification(
                user_id=uid,
                type=type,
                title=title,
                content=content,
                link=link,
            )
            self.db.add(notif)
            self.db.flush()  # 取 notif.id
            if first_id is None:
                first_id = notif.id
            notifications.append(notif)

        self.db.commit()
        for n in notifications:
            self.db.refresh(n)

        # WS 推送 (仿照 create 的格式)
        if push_ws:
            for n in notifications:
                try:
                    await ws_manager.send_to_user(
                        n.user_id,
                        {
                            "type": "notification",
                            "data": {
                                "id": str(n.id),
                                "user_id": n.user_id,
                                "type": n.type,
                                "title": n.title,
                                "content": n.content,
                                "link": n.link,
                                "is_read": n.is_read,
                                "created_at": n.created_at.isoformat() if n.created_at else None,
                            },
                        },
                    )
                except Exception:  # noqa: BLE001
                    logger.exception("WS push failed for user %s", n.user_id)

        # 多通道分发（Phase 1: inbox 已完成；email 写 pending 日志）
        # 用 notifications[0] 作为代表性 log（correlation_id 关联所有用户 + 所有通道）
        dispatcher = NotificationDispatcher(self.db)
        try:
            # notifications 列表里的 id 是同一逻辑通知的多次入库（每用户一行）
            # dispatcher 接受单一 notification + user_ids，对每个 (user, channel) 写 log
            await dispatcher.dispatch(notifications[0], user_ids=user_ids)
        except Exception:  # noqa: BLE001
            logger.exception("dispatcher failed")

        return notifications

    # ============== 查询 ==============

    def list_for_user(
        self,
        user_id: int,
        page: int = 1,
        page_size: int = 20,
        is_read: Optional[bool] = None,
    ) -> tuple[List[Notification], int]:
        """分页获取某用户的通知列表。"""
        stmt = select(Notification).where(Notification.user_id == user_id)
        count_stmt = select(func.count(Notification.id)).where(Notification.user_id == user_id)
        if is_read is not None:
            stmt = stmt.where(Notification.is_read == is_read)
            count_stmt = count_stmt.where(Notification.is_read == is_read)

        total = self.db.execute(count_stmt).scalar() or 0
        items = (
            self.db.execute(
                stmt.order_by(Notification.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
            .scalars()
            .all()
        )
        return list(items), int(total)

    def unread_count(self, user_id: int) -> int:
        stmt = (
            select(func.count(Notification.id))
            .where(Notification.user_id == user_id)
            .where(Notification.is_read == False)  # noqa: E712
        )
        return int(self.db.execute(stmt).scalar() or 0)

    # ============== 更新 ==============

    def mark_read(self, user_id: int, notif_id: UUID) -> bool:
        """标记单条已读（只允许标记本人通知）。返回是否命中并更新。"""
        result = self.db.execute(
            update(Notification)
            .where(Notification.id == notif_id, Notification.user_id == user_id)
            .values(is_read=True)
        )
        self.db.commit()
        return result.rowcount > 0

    def mark_all_read(self, user_id: int) -> int:
        result = self.db.execute(
            update(Notification)
            .where(Notification.user_id == user_id, Notification.is_read == False)  # noqa: E712
            .values(is_read=True)
        )
        self.db.commit()
        return int(result.rowcount or 0)
