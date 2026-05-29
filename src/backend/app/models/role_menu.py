"""
角色菜单关联模型
"""

from sqlalchemy import Column, BigInteger, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.models.base import Base


class RoleMenu(Base):
    """角色菜单关联表"""
    __tablename__ = "soc_role_menus"

    role_id = Column(BigInteger, ForeignKey('soc_roles.id', ondelete='CASCADE'), primary_key=True)
    menu_id = Column(BigInteger, ForeignKey('soc_menus.id', ondelete='CASCADE'), primary_key=True)
    permissions = Column(JSONB, default=list)  #  granted button permissions: ["add", "edit", "delete"]

    def __repr__(self):
        return f"<RoleMenu(role_id={self.role_id}, menu_id={self.menu_id}, permissions={self.permissions})>"
