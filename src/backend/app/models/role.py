"""
角色模型
"""

from sqlalchemy import Column, String, Text, BigInteger, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class Role(Base):
    """角色表"""
    __tablename__ = "soc_roles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), unique=True, nullable=False)
    code = Column(String(50), unique=True, nullable=False)
    description = Column(Text)
    is_system = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    users = relationship("User", back_populates="role")
    role_menus = relationship("RoleMenu", back_populates="role", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Role(id={self.id}, name={self.name}, code={self.code})>"


class RoleMenu(Base):
    """角色菜单关联表"""
    __tablename__ = "soc_role_menus"

    role_id = Column(BigInteger, ForeignKey('soc_roles.id', ondelete='CASCADE'), primary_key=True)
    menu_id = Column(BigInteger, ForeignKey('soc_menus.id', ondelete='CASCADE'), primary_key=True)

    # 关系
    role = relationship("Role", back_populates="role_menus")
    menu = relationship("Menu", back_populates="role_menus")

    def __repr__(self):
        return f"<RoleMenu(role_id={self.role_id}, menu_id={self.menu_id})>"
