"""
资产风险评分历史模型（PRD F1.1 / v1.2 §5.3）

每次批量评分落一条快照，支撑近 90 天趋势折线与"评分上升最快"列表。
"""
from sqlalchemy import Column, Integer, DateTime, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.models.base import Base


class AssetRiskHistory(Base):
    """风险评分历史表（soc_asset_risk_history）"""

    __tablename__ = "soc_asset_risk_history"
    __table_args__ = (
        # 趋势查询：按资产 + 时间倒序取最近 N 条
        Index("idx_soc_asset_risk_history_asset_time", "asset_id", "scored_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("soc_assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    risk_score = Column(Integer, nullable=False)  # 0-100
    score_breakdown = Column(JSONB)               # 与 soc_assets.score_breakdown 同构
    scored_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<AssetRiskHistory(asset_id={self.asset_id}, score={self.risk_score}, at={self.scored_at})>"
