"""
事件模型
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class Incident(Base):
    """事件表"""
    __tablename__ = "soc_incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    title = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(20), nullable=False)  # open, in_progress, resolved, closed
    severity = Column(String(20), nullable=False)  # critical, high, medium, low
    wazuh_alert_id = Column(String(100))
    assigned_to = Column(String(255))
    created_by = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    resolved_at = Column(DateTime(timezone=True))
    resolution_notes = Column(Text)
    ai_analysis_id = Column(UUID(as_uuid=True), ForeignKey("soc_ai_analyses.id", ondelete="SET NULL"))

    # 关系
    assets = relationship("AssetIncident", back_populates="incident")
    ai_analysis = relationship("AIAnalysis", backref="incident")

    def __repr__(self):
        return f"<Incident(id={self.id}, title={self.title}, status={self.status})>"
