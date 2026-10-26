"""
站内通知模型
"""

from sqlalchemy import Column, String, Text, DateTime, Boolean, Integer, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.models.base import Base


class Notification(Base):
    """站内通知表

    type 取值：
      - alert    : 严重告警触发
      - ai_done  : AI 任务完成
      - system   : 系统级广播
      - test     : 管理员手动测试
    """

    __tablename__ = "soc_notifications"
    __table_args__ = (
        Index("ix_soc_notifications_user_created", "user_id", "created_at"),
        Index("ix_soc_notifications_user_unread", "user_id", "is_read"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(Integer, nullable=False, index=True)
    type = Column(String(20), nullable=False)
    title = Column(String(200), nullable=False)
    content = Column(Text)
    link = Column(String(500))
    is_read = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # 2026-10-25 邮件场景模板支持（迁移 b2c3d4e5f6a7）：
    # email_type = 邮件模板键（如 'push:shadow_asset'；NULL 走 type 通用模板）
    # email_ctx  = 模板额外上下文（source_code/down_hours 等，JSONB）
    # worker 异步投递时从这两列取值——进程内参数跨不了 60s tick，必须落库。
    # 仅邮件渲染用，站内信/WS/去重逻辑一概不读。
    email_type = Column(String(40), nullable=True)
    email_ctx = Column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Notification(id={self.id}, user_id={self.user_id}, "
            f"type={self.type}, is_read={self.is_read})>"
        )
