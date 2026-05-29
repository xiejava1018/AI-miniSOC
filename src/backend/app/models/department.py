"""
部门模型
"""

from sqlalchemy import Column, String, BigInteger, DateTime, Integer, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class Department(Base):
    """部门表"""
    __tablename__ = "soc_departments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    parent_id = Column(BigInteger, ForeignKey('soc_departments.id'), nullable=True)
    name = Column(String(50), nullable=False)
    status = Column(Integer, default=1)  # 1=启用, 2=禁用
    sort = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    parent = relationship("Department", remote_side=[id], back_populates="children")
    children = relationship("Department", back_populates="parent", cascade="all, delete-orphan")
    users = relationship("User", back_populates="department")

    def to_dict(self, include_children: bool = False) -> dict:
        """转换为字典格式"""
        data = {
            "id": self.id,
            "parent_id": self.parent_id,
            "name": self.name,
            "status": self.status,
            "sort": self.sort,
            "user_count": len(self.users) if self.users else 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_children and self.children:
            data["children"] = [child.to_dict(include_children=False) for child in sorted(self.children, key=lambda x: x.sort or 0)]
        return data

    def __repr__(self):
        return f"<Department(id={self.id}, name={self.name})>"
