"""
部门模型
"""

from sqlalchemy import Column, String, BigInteger, DateTime, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class Department(Base):
    """部门表"""
    __tablename__ = "soc_departments"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    status = Column(Integer, default=1)  # 1=启用, 2=禁用
    sort = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 关系
    users = relationship("User", back_populates="department")

    def to_dict(self):
        """转换为字典格式"""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "sort": self.sort,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f"<Department(id={self.id}, name={self.name})>"
