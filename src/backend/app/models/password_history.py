"""
密码历史模型
"""

from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class PasswordHistory(Base):
    """密码历史表"""
    __tablename__ = "soc_password_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('soc_users.id', ondelete='CASCADE'), nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # 关系
    user = relationship("User", back_populates="password_history")

    def __repr__(self):
        return f"<PasswordHistory(id={self.id}, user_id={self.user_id}, created_at={self.created_at})>"
