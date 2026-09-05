"""身份管道模型（方案 §4.1 Phase 0 / 层4 关系画像数据源）

soc_identity_events   账号行为事件流（OpenSearch 认证类告警抽取）
soc_identity_bindings 账号 ↔ IP 稳定映射（"xiejava 在用哪些设备 / 这台设备谁在用"）
"""

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, ForeignKey, Index, Integer,
    String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models.base import Base


class IdentityEvent(Base):
    """认证类事件（rule 5715/5501/5502/5760/5763/5551 抽取，每日增量）"""

    __tablename__ = "soc_identity_events"
    __table_args__ = (
        UniqueConstraint("es_index", "es_doc_id", name="uq_identity_event_doc"),
        Index("ix_identity_events_src_ip", "src_ip"),
        Index("ix_identity_events_dst_ip", "dst_ip"),
        Index("ix_identity_events_account", "account"),
        Index("ix_identity_events_ts", "ts"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    es_index = Column(String(64), nullable=False, comment="来源索引（幂等键）")
    es_doc_id = Column(String(64), nullable=False, comment="来源文档 id（幂等键）")
    rule_id = Column(String(16), nullable=True)
    account = Column(String(64), nullable=True, comment="抽取的用户名（失败尝试也保留）")
    src_ip = Column(String(45), nullable=True, comment="操作方（data.srcip）")
    dst_ip = Column(String(45), nullable=True, comment="被登录主机（agent.ip）")
    success = Column(Boolean, nullable=False, default=False)
    event_type = Column(String(16), nullable=False, default="auth",
                        comment="auth_success/auth_failed/session_open/session_close")
    ts = Column(DateTime(timezone=True), nullable=False, comment="事件时间")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class IdentityBinding(Base):
    """账号 ↔ IP 稳定映射（仅统计成功登录）"""

    __tablename__ = "soc_identity_bindings"
    __table_args__ = (
        UniqueConstraint("account", "ip", name="uq_identity_binding_account_ip"),
        Index("ix_identity_bindings_ip", "ip"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    account = Column(String(64), nullable=False)
    ip = Column(String(45), nullable=False, comment="登录目标主机 IP")
    asset_id = Column(UUID(as_uuid=False), ForeignKey("soc_assets.id", ondelete="SET NULL"), nullable=True)
    logins = Column(Integer, nullable=False, default=0, comment="累计成功登录次数")
    first_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
