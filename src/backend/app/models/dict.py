"""
字典模型
"""

from sqlalchemy import Column, String, Text, BigInteger, Integer, DateTime, Boolean, UniqueConstraint
from sqlalchemy.sql import func
from app.models.base import Base


class Dict(Base):
    """数据字典表"""
    __tablename__ = "soc_dicts"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    dict_type = Column(String(50), nullable=False, index=True)
    dict_code = Column(String(50), nullable=False)
    dict_label = Column(String(100), nullable=False)
    color = Column(String(20))
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    is_default = Column(Boolean, default=False)
    remark = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('dict_type', 'dict_code', name='uq_dict_type_code'),
    )

    def __repr__(self):
        return f"<Dict(id={self.id}, type={self.dict_type}, code={self.dict_code})>"
