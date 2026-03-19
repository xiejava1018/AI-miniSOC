"""
用户会话模型
"""

from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class UserSession(Base):
    """用户会话表"""
    __tablename__ = "soc_user_sessions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('soc_users.id', ondelete='CASCADE'), nullable=False)
    token_hash = Column(String(64), nullable=False)
    refresh_token_hash = Column(String(64))
    ip_address = Column(String(45))
    user_agent = Column(String)
    login_at = Column(DateTime(timezone=True), server_default=func.now())
    logout_at = Column(DateTime(timezone=True))
    last_activity_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)

    # 关系
    user = relationship("User", back_populates="sessions")
    audit_logs = relationship("AuditLog", back_populates="session")

    def __repr__(self):
        return f"<UserSession(id={self.id}, user_id={self.user_id}, is_active={self.is_active})>"
