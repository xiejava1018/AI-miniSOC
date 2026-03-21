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
    LOCKED = "locked"
    DISABLED = "disabled"


class User(Base):
    """用户表"""
    __tablename__ = "soc_users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    email = Column(String(100), unique=True)
    full_name = Column(String(100))
    status = Column(String(20), default=UserStatus.ACTIVE)
    role_id = Column(Integer, ForeignKey('soc_roles.id'))
    is_superuser = Column(Boolean, default=False)
    last_login = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    role = relationship("Role", back_populates="users")
    sessions = relationship("UserSession", back_populates="user")
    password_history = relationship("PasswordHistory", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="user")
    password_reset_tokens = relationship("PasswordResetToken", back_populates="user")

    @property
    def is_admin(self) -> bool:
        """判断是否为管理员"""
        return self.role and self.role.code == "admin"

    @property
    def is_locked(self) -> bool:
        """判断账户是否被锁定"""
        return self.status == UserStatus.LOCKED

    def has_menu_access(self, menu_path: str) -> bool:
        """检查用户是否有指定菜单的访问权限"""
        if not self.role or not self.role.menus:
            return False
        return any(menu.path == menu_path for menu in self.role.menus)

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, status={self.status})>"
