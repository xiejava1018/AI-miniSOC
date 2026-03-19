"""
菜单模型
"""

from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey, Boolean, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class Menu(Base):
    """菜单表"""
    __tablename__ = "soc_menus"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    parent_id = Column(BigInteger, ForeignKey('soc_menus.id'))
    name = Column(String(50), nullable=False)
    path = Column(String(200), nullable=False)
    icon = Column(String(50))
    sort_order = Column(Integer, default=0)
    is_visible = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    parent = relationship("Menu", remote_side=[id], back_populates="children")
    children = relationship("Menu", back_populates="parent", cascade="all, delete-orphan")
    role_menus = relationship("RoleMenu", back_populates="menu")
    roles = relationship("Role", secondary="soc_role_menus", back_populates="menus")

    def to_dict(self, include_children: bool = False):
        """转换为字典格式"""
        data = {
            "id": self.id,
            "parent_id": self.parent_id,
            "name": self.name,
            "path": self.path,
            "icon": self.icon,
            "sort_order": self.sort_order,
            "is_visible": self.is_visible,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_children and self.children:
            data["children"] = [child.to_dict(include_children=False) for child in sorted(self.children, key=lambda x: x.sort_order)]
        return data

    def __repr__(self):
        return f"<Menu(id={self.id}, name={self.name}, path={self.path})>"
