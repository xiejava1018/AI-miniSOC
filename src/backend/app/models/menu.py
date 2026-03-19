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

    def __repr__(self):
        return f"<Menu(id={self.id}, name={self.name}, path={self.path})>"
