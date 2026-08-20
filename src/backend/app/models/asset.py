"""
资产模型
"""

from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, MACADDR, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class Asset(Base):
    """资产表"""
    __tablename__ = "soc_assets"
    __table_args__ = (
        UniqueConstraint('network_segment', 'asset_ip', name='uq_network_segment_ip'),
        # T0a：wazuh_agent_id 唯一部分索引（NULL 不受约束），防 agent 双挂串数据
        Index('uq_soc_assets_agent_id', 'wazuh_agent_id', unique=True,
              postgresql_where='wazuh_agent_id IS NOT NULL'),
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

    # P3/F1.1（2026-08-21，PRD v1.2.1）：AI 资产风险评分（规则引擎计算，不调 GLM）
    # risk_score: 0-100；NULL 表示未评分或数据全缺失（N/A，不误导为"0 分很安全"）
    risk_score = Column(Integer)
    risk_summary = Column(Text)      # GLM 一句话摘要（仅 score>=60 或快速上升资产，24h 缓存）
    risk_scored_at = Column(DateTime(timezone=True))
    score_breakdown = Column(JSONB)  # 各维度得分/权重/命中规则（可解释性，PRD §八-C）

    # 关系
    ports = relationship("AssetPort", backref="asset", cascade="all, delete-orphan")
    tags = relationship("AssetTag", backref="asset", cascade="all, delete-orphan")

    # 关系 - 暂时注释掉，因为soc_asset_incidents表不存在
    # incidents = relationship("AssetIncident", back_populates="asset")

    def __repr__(self):
        return f"<Asset(id={self.id}, name={self.name}, ip={self.asset_ip})>"
