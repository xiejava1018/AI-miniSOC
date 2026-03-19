"""
API限流模型
"""

from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class RateLimit(Base):
    """API限流表"""
    __tablename__ = "soc_rate_limits"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey('soc_users.id'))
    ip_address = Column(String(45), nullable=False)
    endpoint = Column(String(200), nullable=False)
    request_count = Column(Integer, default=1)
    window_start = Column(DateTime(timezone=True), server_default=func.now())
    blocked_until = Column(DateTime(timezone=True))

    # 关系
    user = relationship("User")

    def __repr__(self):
        return f"<RateLimit(id={self.id}, ip_address={self.ip_address}, endpoint={self.endpoint})>"
