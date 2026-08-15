"""
CISA KEV（Known Exploited Vulnerabilities）本地缓存模型

T6（§12.2，2026-08-15 决策2）：点亮 AI 评分"在野利用 15%"权重。
表 soc_cisa_kev 由 scripts/backfill_vulnerability_contract.py 创建
（alembic 迁移图已损坏，本期 DB 变更一律走 scripts，§14.4）。
"""

from sqlalchemy import Column, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.models.base import Base


class CisaKev(Base):
    """CISA KEV 目录条目（cve_id 全局唯一）"""
    __tablename__ = "soc_cisa_kev"

    cve_id = Column(String(50), primary_key=True)
    date_added = Column(DateTime(timezone=True))       # CISA 收录时间
    short_description = Column(Text)                   # 简述（vulnerabilityName + product）
    required_action = Column(Text)                     # 要求的处置动作
    due_date = Column(DateTime(timezone=True))         # 联邦机构修复时限
    known_ransomware = Column(Boolean, nullable=False, default=False)  # 是否被勒索软件利用
    notes = Column(Text)
    synced_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<CisaKev(cve_id={self.cve_id}, ransomware={self.known_ransomware})>"
