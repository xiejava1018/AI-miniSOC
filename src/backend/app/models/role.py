"""
角色模型
"""

from enum import Enum
from sqlalchemy import Column, String, Text, BigInteger, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class RoleCode(str, Enum):
    """角色代码枚举"""
    ADMIN = "admin"
    USER = "user"
    READONLY = "readonly"


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
    menus = relationship("Menu", secondary="soc_role_menus", back_populates="roles")

    def __repr__(self):
        return f"<Role(id={self.id}, name={self.name}, code={self.code})>"
