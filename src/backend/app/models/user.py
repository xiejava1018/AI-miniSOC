"""
用户模型
"""

from enum import Enum
from sqlalchemy import Column, String, Integer, BigInteger, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class UserStatus(str, Enum):
    """用户状态枚举"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"
    PENDING = "pending"


class User(Base):
    """用户表"""
    __tablename__ = "soc_users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(100), unique=True)
    full_name = Column(String(100))
    status = Column(String(20), default=UserStatus.ACTIVE)
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
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user")

    @property
    def is_admin(self) -> bool:
        """判断是否为管理员"""
        return self.role and self.role.code == "admin"

    @property
    def is_locked(self) -> bool:
        """判断账户是否被锁定"""
        from datetime import datetime
        if self.status == UserStatus.LOCKED:
            return True
        if self.locked_until and self.locked_until > datetime.now(self.locked_until.tzinfo):
            return True
        return False

    def has_menu_access(self, menu_path: str) -> bool:
        """检查用户是否有指定菜单的访问权限"""
        if not self.role or not self.role.menus:
            return False
        return any(menu.path == menu_path for menu in self.role.menus)

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, status={self.status})>"
