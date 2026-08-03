"""
上网行为异常检测 - 恶意域名黑名单模型
"""

from sqlalchemy import Column, String, BigInteger, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.models.base import Base


class BrowsingBlacklist(Base):
    """恶意域名黑名单表

    来源：
      - manual：管理员手动添加
      - threat_intel：威胁情报同步（二期）
    支持通配符，如 *.evil.com
    """
    __tablename__ = "soc_browsing_blacklist"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    domain = Column(String(255), nullable=False, unique=True, index=True)
    source = Column(String(50), nullable=False, default="manual")
    reason = Column(String(255), nullable=True)
    created_by = Column(BigInteger, ForeignKey("soc_users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<BrowsingBlacklist(id={self.id}, domain={self.domain}, source={self.source})>"
