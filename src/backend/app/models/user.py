"""
用户模型
"""

from sqlalchemy import Column, String, Integer, BigInteger, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class User(Base):
    """用户表"""
    __tablename__ = "soc_users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(100), unique=True)
    full_name = Column(String(100))
    status = Column(String(20), default='active')
    role_id = Column(BigInteger, ForeignKey('soc_roles.id'), nullable=False)
    last_login_at = Column(DateTime(timezone=True))
    password_changed_at = Column(DateTime(timezone=True))
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    role = relationship("Role", back_populates="users")
    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
    password_history = relationship("PasswordHistory", back_populates="user", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="user")
    rate_limits = relationship("RateLimit", back_populates="user")
    system_configs = relationship("SystemConfig", back_populates="updated_by_user")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, status={self.status})>"


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
