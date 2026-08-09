"""
告警簇 AI 研判模型

Phase 1：对"一个告警簇"（rule.id|agent.id 聚合）做结构化 AI 研判，
独立于 soc_ai_analyses（后者为单条告警语义）。按 fingerprint 唯一缓存 + 7 天 TTL。
无 AI 配额时 source='heuristic' 兜底，界面与 MCP 照常工作。
"""
from sqlalchemy import Column, String, Text, DateTime, Integer, Boolean, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.models.base import Base


class AlertGroupAnalysis(Base):
    """告警簇 AI 研判缓存表（soc_alert_group_analyses）"""

    __tablename__ = "soc_alert_group_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    # 簇指纹（缓存主键）：rule_id|agent_id，可逆解析
    fingerprint = Column(String(255), nullable=False, unique=True, index=True)
    # 研判时的快照（审计用）
    rule_id = Column(String(64), nullable=True)
    agent_id = Column(String(64), nullable=True)
    rule_description = Column(Text, nullable=True)

    # —— 结构化研判结论 ——
    priority = Column(String(4), nullable=False, default="P3")  # P0/P1/P2/P3
    is_noise = Column(Boolean, nullable=False, default=False)
    confidence = Column(Float, nullable=False, default=0.0)
    rationale = Column(Text, nullable=True)
    recommended_action = Column(Text, nullable=True)
    suggest_incident = Column(Boolean, nullable=False, default=False)

    # —— 来源与元数据 ——
    source = Column(String(16), nullable=False, default="heuristic")  # agent / zhipu / heuristic
    model_name = Column(String(50), nullable=True)
    window_hours = Column(Integer, nullable=True)
    linked_asset_id = Column(
        UUID(as_uuid=True), ForeignKey("soc_assets.id"), nullable=True, index=True
    )

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=True)

    def to_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "rule_id": self.rule_id,
            "agent_id": self.agent_id,
            "rule_description": self.rule_description,
            "priority": self.priority,
            "is_noise": self.is_noise,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "recommended_action": self.recommended_action,
            "suggest_incident": self.suggest_incident,
            "source": self.source,
            "model_name": self.model_name,
            "window_hours": self.window_hours,
            "linked_asset_id": str(self.linked_asset_id) if self.linked_asset_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
