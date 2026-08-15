"""
资产模型
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, MACADDR, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class Asset(Base):
    """资产表"""
    __tablename__ = "soc_assets"
    __table_args__ = (
        UniqueConstraint('network_segment', 'asset_ip', name='uq_network_segment_ip'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    network_segment = Column(String(50), nullable=False, default="default")
    network_zone = Column(String(50), default="other")
    asset_ip = Column(Text, nullable=False)
    asset_description = Column(Text)
    asset_status = Column(String)
    status_updated_at = Column(DateTime(timezone=True))
    parent_id = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 数据同步相关字段
    data_source = Column(String(20), default="manual")  # 'manual', 'wazuh', 'tplink-router'
    last_synced_at = Column(DateTime(timezone=True))
    os_name = Column(String(100))
    os_version = Column(String(100))
    hardware_info = Column(JSONB)

    name = Column(String(255))
    mac_address = Column(MACADDR)
    asset_type = Column(String(50), default="other")
    # 决策1（2026-08-15）：criticality 统一四档 critical/high/medium/low（存量 'normal' 已回填 'medium'）
    # 前端展示经字典 asset_criticality 中文化（严重/高/中/低），与 vulnerability_ai.CRITICALITY_SCORES 对齐
    criticality = Column(String(20), default="medium")
    owner = Column(String(255))
    business_unit = Column(String(255))
    wazuh_agent_id = Column(String(100))

    # 合规 + 应急联系字段(详情页 v2 引入)
    data_classification = Column(String(20), default="internal")  # public/internal/confidential/secret
    owner_contact = Column(String(50))  # 负责人联系电话

    # T3（2026-08-15）：暴露面等级，供漏洞 AI 评分（vulnerability_ai.EXPOSURE_SCORES）使用。
    # DB 列已由迁移 b2c4d6e7f8a9 建好（NOT NULL 默认 'internal'），此处仅为 ORM 补声明，
    # 否则 ai-suggestions / score-breakdown 访问 Asset.exposure_level 即 AttributeError → 500。
    # 取值：public（公网暴露）/ internal（内网）/ isolated（隔离网络）
    exposure_level = Column(String(20), default="internal", server_default="internal")

    # 关系
    ports = relationship("AssetPort", backref="asset", cascade="all, delete-orphan")
    tags = relationship("AssetTag", backref="asset", cascade="all, delete-orphan")

    # 关系 - 暂时注释掉，因为soc_asset_incidents表不存在
    # incidents = relationship("AssetIncident", back_populates="asset")

    def __repr__(self):
        return f"<Asset(id={self.id}, name={self.name}, ip={self.asset_ip})>"
