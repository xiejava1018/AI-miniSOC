"""
上网行为异常检测 - IP×域名基线模型
"""

from sqlalchemy import Column, String, BigInteger, DateTime, UniqueConstraint, Index
from sqlalchemy.sql import func

from app.models.base import Base


class BrowsingBaseline(Base):
    """IP×域名访问基线表

    用于 R3「基线偏离」检测：访问历史(7天)未见过的域名即视为偏离。
    按 (ip, domain) 唯一，滚动更新 first_seen / last_seen / total_count。
    """
    __tablename__ = "soc_browsing_baseline"
    __table_args__ = (
        UniqueConstraint("ip", "domain", name="uq_browsing_baseline_ip_domain"),
        Index("ix_browsing_baseline_ip", "ip"),
        Index("ix_browsing_baseline_last_seen", "last_seen"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    ip = Column(String(45), nullable=False)
    domain = Column(String(500), nullable=False)
    first_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    total_count = Column(BigInteger, nullable=False, default=1)

    def __repr__(self):
        return f"<BrowsingBaseline(ip={self.ip}, domain={self.domain}, count={self.total_count})>"
