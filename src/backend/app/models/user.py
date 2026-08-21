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
    nick_name = Column(String(100))
    phone = Column(String(20))
    avatar = Column(String(255))
    gender = Column(Integer, default=0)  # 0=未知, 1=男, 2=女
    status = Column(String(20), default=UserStatus.ACTIVE)
    role_id = Column(Integer, ForeignKey('soc_roles.id'))
    department_id = Column(BigInteger, ForeignKey('soc_departments.id'))
    is_superuser = Column(Boolean, default=False)
    last_login = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    role = relationship("Role", back_populates="users")
    department = relationship("Department", back_populates="users")
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

    def has_button_access(self, menu_path: str, button: str) -> bool:
        """检查用户对指定菜单的某个按钮（authMark）是否有权限。

        依赖 RoleMenu.permissions JSONB 数组（迁移里种），
        例：role_menu.permissions = '["view", "reconcile", "resolve"]'
        调用例：user.has_button_access('/asset/reconciliation', 'resolve') => True/False

        注意：path 可能多菜单匹配（如 'list' 在 /assets 和 /reports 都有），
        所以检查路径'path 在多个菜单里、任一一个菜单含 button 就返 True。
        """
        if self.is_admin:
            return True
        if not self.role:
            return False
        from app.models import RoleMenu, Menu
        session = self.role._sa_instance_state.session
        rows = (
            session.query(RoleMenu.permissions)
            .join(Menu, Menu.id == RoleMenu.menu_id)
            .filter(Menu.path == menu_path, RoleMenu.role_id == self.role_id)
            .all()
        ) if self.role_id else []
        if not rows:
            return False
        import json
        for perms in [r[0] for r in rows]:
            if isinstance(perms, str):
                try:
                    perms = json.loads(perms)
                except (ValueError, TypeError):
                    continue
            if button in (perms or []):
                return True
        return False

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, status={self.status})>"
