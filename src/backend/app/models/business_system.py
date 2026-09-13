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
    criticality = Column(String(20), nullable=False, default="medium",
                          comment="critical|high|medium|low，与 asset 对齐")
    # ⚠️ soc_users.id 是 Integer（非 UUID）
    owner_id = Column(Integer, ForeignKey("soc_users.id", ondelete="SET NULL"), nullable=True)
    # ⚠️ soc_departments.id 是 BigInteger（非 UUID）
    department_id = Column(BigInteger, ForeignKey("soc_departments.id", ondelete="SET NULL"),
                           nullable=True)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now(), onupdate=func.now())

    # 关系
    owner = relationship("User", foreign_keys=[owner_id])
    department = relationship("Department", foreign_keys=[department_id])
    asset_links = relationship("AssetBusiness", back_populates="system",
                               cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "code": self.code,
            "name": self.name,
            "criticality": self.criticality,
            "owner_id": self.owner_id,
            "owner_username": self.owner.username if self.owner else None,
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

    def to_dict(self) -> dict:
        return {
            "asset_id": str(self.asset_id),
            "system_id": str(self.system_id),
            "role": self.role,
        }