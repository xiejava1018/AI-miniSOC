"""
业务系统模型（资产知识图谱 v1）

新增表：
  - soc_business_systems     业务系统实体
  - soc_asset_business       资产 ↔ 业务系统 多对多

详见 docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6.2③
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger, Column, DateTime, ForeignKey, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class BusinessSystem(Base):
    """业务系统实体（补齐"资产→业务→部门→责任人"主链的关键）"""
    __tablename__ = "soc_business_systems"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    code = Column(Text, unique=True, nullable=False, comment="业务系统唯一编码，如 'soc-platform'")
    name = Column(Text, nullable=False)
    # === 重要性三维分解（治本方案 · 2026-09-14）===========================
    # 业务系统侧只保留 3 个新字段；criticality 列保留 6 个月过渡期（读时自动派生）。
    # 详见 app/core/criticality.py 第一性原理说明。
    #
    # business_impact：业务影响 5 档（业务系统维度，5 档 core/important/normal/auxiliary/ignorable）
    business_impact = Column(
        String(20),
        nullable=False,
        default="normal",
        server_default="normal",
        comment="业务影响 5 档，详见 app/core/criticality.py",
    )
    # data_sensitivity：数据敏感度（CIA 维度，5 档）
    data_sensitivity = Column(
        String(20),
        nullable=False,
        default="medium",
        server_default="medium",
        comment="数据敏感度 5 档，进风险评分",
    )
    # protection_level：等保等级（5 档 level_5~level_1，合规锚点）
    protection_level = Column(
        String(20),
        nullable=False,
        default="level_2",
        server_default="level_2",
        comment="等保等级 5 档，资产继承此值",
    )
    # criticality：DEPRECATED（6 个月过渡期）
    criticality = Column(
        String(20),
        nullable=False,
        default="medium",
        server_default="medium",
        comment="DEPRECATED: 改用 business_impact + data_sensitivity + protection_level",
    )
    # ⚠️ soc_users.id 是 Integer（非 UUID）。owner_id 是「平台用户」外键（可选，关联用）。
    owner_id = Column(Integer, ForeignKey("soc_users.id", ondelete="SET NULL",), nullable=True)
    # ⚠️ soc_departments.id 是 BigInteger（非 UUID）
    department_id = Column(BigInteger, ForeignKey("soc_departments.id", ondelete="SET NULL"),
                           nullable=True)
    # v1.1（2026-09-14）：责任人改为「自由文本姓名」，与 asset.owner 对齐——
    # 业务系统责任人可能不是 SOC 平台用户，不能用 owner_id FK 强约束。
    # owner 文本列与下方 owner_user relationship 分开（asset 表同款模式）。
    owner = Column(String(255), comment="责任人姓名（自由文本，可不填平台用户）")
    owner_contact = Column(String(50), comment="责任人联系电话（安全风险应急联系用）")
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now(), onupdate=func.now())

    # 关系
    owner_user = relationship("User", foreign_keys=[owner_id])
    department = relationship("Department", foreign_keys=[department_id])
    asset_links = relationship("AssetBusiness", back_populates="system",
                               cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        from app.core.criticality import legacy_criticality_from_data_sensitivity
        return {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "business_impact": self.business_impact,
            "data_sensitivity": self.data_sensitivity,
            "protection_level": self.protection_level,
            # criticality：派生字段（deprecated alias 读时自动计算，写入关闭）
            "criticality": self.criticality or legacy_criticality_from_data_sensitivity(self.data_sensitivity),
            "owner_id": self.owner_id,
            "owner": self.owner,
            "owner_contact": self.owner_contact,
            "owner_username": self.owner_user.username if self.owner_user else None,
            "department_id": self.department_id,
            "department_name": self.department.name if self.department else None,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class AssetBusiness(Base):
    """资产 ↔ 业务系统 多对多"""
    __tablename__ = "soc_asset_business"
    __table_args__ = (
        UniqueConstraint("asset_id", "system_id", name="uq_asset_business"),
    )

    asset_id = Column(UUID(as_uuid=True),
                      ForeignKey("soc_assets.id", ondelete="CASCADE"),
                      primary_key=True, nullable=False)
    system_id = Column(UUID(as_uuid=True),
                       ForeignKey("soc_business_systems.id", ondelete="CASCADE"),
                       primary_key=True, nullable=False)
    role = Column(String(50), comment="web|app|db|mq|cache|gateway")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    # 关系
    system = relationship("BusinessSystem", back_populates="asset_links")
    # Asset.business_links 已在 asset.py 定义（back_populates='asset'）
    asset = relationship("Asset", back_populates="business_links")

    def to_dict(self) -> dict:
        return {
            "asset_id": str(self.asset_id),
            "system_id": str(self.system_id),
            "role": self.role,
        }