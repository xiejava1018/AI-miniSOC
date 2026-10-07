"""
通知通道扩展模型（OH-NOT-F2 · Phase 1）

CLAUDE.md §0/§1.2 一表前缀 + §3.2 模块化。

设计要点：
- NotificationChannel: 多通道定义（inbox 预置 + email 模板 + 未来 sms/webhook）
- NotificationDispatchLog: 每通道投递日志（pending/sent/failed/bounced/skipped_pref）
- UserNotificationPreference: 用户 per (type, channel) 偏好（默认全收）
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.models.base import Base


class EmailTemplateOverride(Base):
    """邮件模板 DB 覆盖（OH-NOT-F2 Phase 3）

    type 唯一；enabled=true 时覆盖内置同名模板（str.format 语法）；
    删除行或 enabled=false 回退内置。渲染层自动 escape 防 XSS。
    """

    __tablename__ = "soc_email_templates"

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    type = Column(String(64), nullable=False, unique=True)
    subject_tmpl = Column(Text, nullable=False)
    text_tmpl = Column(Text, nullable=False)
    html_tmpl = Column(Text, nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<EmailTemplateOverride type={self.type!r} enabled={self.enabled}>"


class NotificationChannel(Base):
    """通知通道字典（inbox / email / 未来 sms/webhook）"""

    __tablename__ = "soc_notification_channels"
    __table_args__ = (
        CheckConstraint("code = LOWER(code)", name="ck_soc_notif_channels_code_lowercase"),
    )

    id = Column(SmallInteger, primary_key=True, autoincrement=True)
    code = Column(String(16), nullable=False, unique=True)
    name = Column(String(50), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    config_json = Column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<NotificationChannel id={self.id} code={self.code!r} enabled={self.enabled}>"


class NotificationDispatchLog(Base):
    """每通道投递日志 — 用于重试/审计/告警"""

    __tablename__ = "soc_notification_dispatch_logs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','sent','failed','bounced','skipped_pref')",
            name="ck_soc_dispatch_status",
        ),
        CheckConstraint(
            "channel_code = LOWER(channel_code)",
            name="ck_soc_dispatch_channel_code",
        ),
        Index("ix_soc_dispatch_user_channel_sent", "user_id", "channel_code", "sent_at"),
        Index(
            "ix_soc_dispatch_status_next_retry",
            "status",
            "next_retry_at",
            postgresql_where="status IN ('pending','failed')",
        ),
        Index(
            "ix_soc_dispatch_notification",
            "notification_id",
            postgresql_where="notification_id IS NOT NULL",
        ),
    )

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    notification_id = Column(
        UUID,
        # FK → soc_notifications.id 通过 alembic 迁移 DDL 强加（不能 SQLAlchemy FK 因为
        # soc_notifications 是另一个 model 不能直接跨文件 import 引用）
        nullable=True,
    )
    user_id = Column(Integer, nullable=False)
    channel_code = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="pending")
    error_text = Column(Text, nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    retry_count = Column(Integer, nullable=False, default=0)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    correlation_id = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<NotificationDispatchLog id={self.id} channel={self.channel_code!r} "
            f"status={self.status!r} user_id={self.user_id}>"
        )


class UserNotificationPreference(Base):
    """用户对特定 (type, channel) 是否启用。

    默认空表 = 用户对所有 (type, channel) 都接收通知（CLAUDE.md §0 X1 矩阵）。
    enabled=false 行 = 用户主动禁 — dispatcher 跳过该 (user, type, channel) 投递。
    """

    __tablename__ = "soc_notification_user_prefs"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "type", "channel_code",
            name="uq_soc_notif_pref_user_type_channel",
        ),
        Index("ix_soc_notif_pref_user", "user_id"),
    )

    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(
        Integer,
        ForeignKey("soc_users.id", ondelete="CASCADE"),
        nullable=False,
    )
    type = Column(String(64), nullable=False)
    channel_code = Column(String(16), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<UserNotificationPreference user_id={self.user_id} type={self.type!r} "
            f"channel={self.channel_code!r} enabled={self.enabled}>"
        )