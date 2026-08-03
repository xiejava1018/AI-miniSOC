"""
上网行为异常检测 - 事件模型
"""

from sqlalchemy import Column, String, Text, DateTime, Integer, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class BrowsingEvent(Base):
    """上网行为异常事件表

    检测引擎输出，每条记录代表一个 (ip, domain) 在某窗口内命中的异常。
    """
    __tablename__ = "soc_browsing_events"
    __table_args__ = (
        Index("ix_browsing_events_ip_domain", "ip", "domain"),
        Index("ix_browsing_events_created", "created_at"),
        Index("ix_browsing_events_status", "status"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    # 异常源 IP（内网设备）
    ip = Column(String(45), nullable=False, index=True)
    # 异常域名
    domain = Column(String(500), nullable=False, index=True)
    # 相关应用类型（如有）
    apptype = Column(String(50), nullable=True)
    # 触发分值
    score = Column(Integer, nullable=False)
    # 严重等级 critical/high/medium/low
    severity = Column(String(20), nullable=False)
    # 命中的规则列表 [{"rule":"R2","weight":40,"detail":"..."}]
    rule_hits = Column(JSONB, nullable=False)
    # 窗口内原始日志条数
    source_count = Column(Integer, nullable=False, default=0)
    # 检测窗口
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    # 状态 new/confirmed/false_positive/resolved/ignored
    status = Column(String(20), nullable=False, default="new")
    # 关联事件（升级到 soc_incidents 时记录）
    incident_id = Column(UUID(as_uuid=True), index=True, nullable=True)
    # AI 研判结果（二期）
    ai_analysis_id = Column(UUID(as_uuid=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolution_note = Column(Text, nullable=True)

    def __repr__(self):
        return f"<BrowsingEvent(id={self.id}, ip={self.ip}, domain={self.domain}, score={self.score})>"
