"""
AI分析模型
"""

from sqlalchemy import Column, String, Text, DateTime, Integer, Numeric
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.models.base import Base


class AIAnalysis(Base):
    """AI分析缓存表"""
    __tablename__ = "soc_ai_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    alert_id = Column(String(100), nullable=False, unique=True)
    alert_fingerprint = Column(String(100))
    explanation = Column(Text)
    risk_assessment = Column(Text)
    recommendations = Column(Text)
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(50))
    tokens_used = Column(Integer)
    cost = Column(Numeric(10, 4))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    expires_at = Column(DateTime(timezone=True))

    def __repr__(self):
        return f"<AIAnalysis(id={self.id}, alert_id={self.alert_id}, model={self.model_name})>"
