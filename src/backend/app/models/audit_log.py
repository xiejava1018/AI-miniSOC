"""
审计日志模型
"""

from sqlalchemy import Column, String, Text, BigInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class AuditLog(Base):
    """审计日志表"""
    __tablename__ = "soc_audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('soc_users.id'))
    username = Column(String(50), nullable=False)
    action = Column(String(50), nullable=False)
    resource_type = Column(String(50))
    resource_id = Column(BigInteger)
    resource_name = Column(String(200))
    old_values = Column(JSONB)
    new_values = Column(JSONB)
    ip_address = Column(String(45))
    user_agent = Column(Text)
    session_id = Column(BigInteger, ForeignKey('soc_user_sessions.id'))
    request_id = Column(String(36))
    status = Column(String(20), default='success')
    error_message = Column(Text)
    log_hash = Column(String(64))
    prev_log_hash = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    user = relationship("User", back_populates="audit_logs", cascade="all, delete-orphan")
    session = relationship("UserSession", back_populates="audit_logs", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AuditLog(id={self.id}, username={self.username}, action={self.action})>"
