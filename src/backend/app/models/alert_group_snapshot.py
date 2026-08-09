"""
告警簇快照模型

方案 B：把每次聚合得到的"告警簇"按周期落库为快照，
支撑历史查询 / 趋势对比。与方案 A 的实时聚合互不干扰。
"""
from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.models.base import Base


class AlertGroupSnapshot(Base):
    """告警簇快照表（soc_alert_groups）"""

    __tablename__ = "soc_alert_groups"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    # 这批快照的采集时间（UTC），同一批次的簇共享同一 snapshot_at
    snapshot_at = Column(DateTime(timezone=True), nullable=False, index=True)
    # 采集窗口（小时），例如 24
    window_hours = Column(Integer, nullable=False, default=24)

    # —— 来自实时聚合 get_alert_groups 的簇字段 ——
    fingerprint = Column(String(255), nullable=False, index=True)
    rule_id = Column(String(64), nullable=True)
    rule_description = Column(Text, nullable=True)
    agent_id = Column(String(64), nullable=True)
    agent_name = Column(String(255), nullable=True)
    agent_ip = Column(Text, nullable=True, index=True)
    count = Column(Integer, nullable=False, default=0)
    level_min = Column(Integer, nullable=True)
    level_max = Column(Integer, nullable=True)
    first_seen = Column(Text, nullable=True)
    last_seen = Column(Text, nullable=True)
    distinct_srcips = Column(Integer, nullable=True)
    top_srcips = Column(JSONB, nullable=True)

    # IP → 资产关联（落库时按 agent_ip 匹配 soc_assets.asset_ip）
    linked_asset_id = Column(
        UUID(as_uuid=True), ForeignKey("soc_assets.id"), nullable=True, index=True
    )

    # —— Phase 1：历史快照回填的 AI verdict（落库时按 fingerprint 查缓存，不重新调 AI）——
    ai_priority = Column(String(4), nullable=True)  # P0/P1/P2/P3
    ai_is_noise = Column(Boolean, nullable=True)
    ai_suggest_incident = Column(Boolean, nullable=True)
    ai_verdict_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "snapshot_at": self.snapshot_at.isoformat() if self.snapshot_at else None,
            "window_hours": self.window_hours,
            "fingerprint": self.fingerprint,
            "rule_id": self.rule_id,
            "rule_description": self.rule_description,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_ip": self.agent_ip,
            "count": self.count,
            "level_min": self.level_min,
            "level_max": self.level_max,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "distinct_srcips": self.distinct_srcips,
            "top_srcips": self.top_srcips,
            "linked_asset_id": str(self.linked_asset_id) if self.linked_asset_id else None,
            "ai_priority": self.ai_priority,
            "ai_is_noise": self.ai_is_noise,
            "ai_suggest_incident": self.ai_suggest_incident,
            "ai_verdict_at": self.ai_verdict_at.isoformat() if self.ai_verdict_at else None,
        }
