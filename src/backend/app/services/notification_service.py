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
        """入库并（可选）通过 WS 实时推送给目标用户。"""
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
