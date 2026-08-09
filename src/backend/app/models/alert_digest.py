"""
告警摘要模型

存储按周期（每日/每周）生成的告警治理摘要：聚合后的告警簇、高频资产、
趋势与时间窗。Phase0 用模板生成 summary_text；Phase1 起由 AI 生成。
"""
from sqlalchemy import Column, String, Text, DateTime, Integer
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.models.base import Base


class AlertDigest(Base):
    """告警摘要表（soc_alert_digests）"""
    __tablename__ = "soc_alert_digests"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    period_type = Column(String(10), nullable=False, default="daily")  # daily / weekly
    period_start = Column(DateTime(timezone=True))
    period_end = Column(DateTime(timezone=True))

    total_alerts = Column(Integer, default=0)
    by_level = Column(JSONB)        # 等级分布 [{level, count}]
    top_groups = Column(JSONB)      # Top 告警簇（含 fingerprint / count / 资产关联）
    top_assets = Column(JSONB)      # 高频资产（含资产名/重要度）
    trend = Column(JSONB)           # 时间序列 [{hour, total, critical}]

    summary_text = Column(Text)     # 自然语言摘要（Phase0 模板；Phase1 AI）
    ai_model = Column(String(50), default="template")

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "period_type": self.period_type,
            "period_start": self.period_start.isoformat() if self.period_start else None,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "total_alerts": self.total_alerts,
            "by_level": self.by_level,
            "top_groups": self.top_groups,
            "top_assets": self.top_assets,
            "trend": self.trend,
            "summary_text": self.summary_text,
            "ai_model": self.ai_model,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<AlertDigest(id={self.id}, type={self.period_type}, total={self.total_alerts})>"
