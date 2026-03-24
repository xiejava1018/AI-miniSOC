"""
资产标签模型
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class AssetTag(Base):
    """资产标签表"""
    __tablename__ = "soc_asset_tags"
    __table_args__ = (
        UniqueConstraint('asset_id', 'tag_key', name='uq_asset_tag_key'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    asset_id = Column(UUID(as_uuid=True), ForeignKey('soc_assets.id', ondelete='CASCADE'), nullable=False)
    tag_key = Column(String(50), nullable=False)  # environment, business_system, location, team
    tag_value = Column(String(100), nullable=False)  # production, hr-system, beijing, backend
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AssetTag(asset_id={self.asset_id}, key={self.tag_key}, value={self.tag_value})>"
