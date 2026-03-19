"""
资产-事件关联模型
"""

from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.models.base import Base


class AssetIncident(Base):
    """资产-事件关联表"""
    __tablename__ = "soc_asset_incidents"

    asset_id = Column(UUID(as_uuid=True), ForeignKey("soc_assets.id", ondelete="CASCADE"), primary_key=True)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("soc_incidents.id", ondelete="CASCADE"), primary_key=True)

    # 关系
    asset = relationship("Asset", back_populates="incidents")
    incident = relationship("Incident", back_populates="assets")

    def __repr__(self):
        return f"<AssetIncident(asset_id={self.asset_id}, incident_id={self.incident_id})>"
