"""
系统配置模型
"""

from sqlalchemy import Column, String, Text, BigInteger, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class SystemConfig(Base):
    """系统配置表"""
    __tablename__ = "soc_system_config"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False)
    key = Column(String(100), nullable=False)
    value = Column(Text)
    value_type = Column(String(20), default='string')
    is_encrypted = Column(Boolean, default=False)
    description = Column(Text)
    updated_by = Column(BigInteger, ForeignKey('soc_users.id'))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<SystemConfig(id={self.id}, category={self.category}, key={self.key})>"
