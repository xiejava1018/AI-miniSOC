"""
资产模型
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, MACADDR
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class Asset(Base):
    """资产表"""
    __tablename__ = "soc_assets"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    asset_ip = Column(Text, nullable=False, unique=True)
    asset_description = Column(Text)
    asset_status = Column(String)
    status_updated_at = Column(DateTime(timezone=True))
    parent_id = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    name = Column(String(255))
    mac_address = Column(MACADDR)
    asset_type = Column(String(50), default="other")
    criticality = Column(String(20), default="medium")
    owner = Column(String(255))
    business_unit = Column(String(255))
    wazuh_agent_id = Column(String(100))

    # 关系
    incidents = relationship("AssetIncident", back_populates="asset")

    def __repr__(self):
        return f"<Asset(id={self.id}, name={self.name}, ip={self.asset_ip})>"
