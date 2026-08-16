"""
数据源健康表模型（P2-T3）
"""
from sqlalchemy import Column, String, BigInteger, Integer, Text, DateTime
from sqlalchemy.sql import func

from app.models.base import Base


class SourceHealth(Base):
    """数据源健康状态记录表（soc_source_health）"""
    __tablename__ = "soc_source_health"

    source_key = Column(String(100), primary_key=True)        # 例如 "loki:browsing_detection"
    source_type = Column(String(50), nullable=False)          # loki / opensearch / tplink_collector / ...
    display_name = Column(String(200))
    last_success_at = Column(DateTime(timezone=True))
    last_failure_at = Column(DateTime(timezone=True))
    last_failure_message = Column(Text)
    success_count = Column(BigInteger, nullable=False, default=0)
    failure_count = Column(BigInteger, nullable=False, default=0)
    expected_interval_seconds = Column(Integer)
    last_records_count = Column(Integer)
    notes = Column(Text)
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<SourceHealth(key={self.source_key}, type={self.source_type}, success={self.success_count}, fail={self.failure_count})>"