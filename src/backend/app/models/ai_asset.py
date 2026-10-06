"""AI 资产六类建模（OH-4.13 · S13）

v1.2 增补，16 号 AI 安全台账对齐。六类共用单表 + kind 枚举 + details
JSONB（类型特定字段）。L 验收是「六类建表 + 迁移」，下游场景（影子 AI
发现 / AI 资产视图）独立任务，本模块只落地数据底座。

六类：
  model       模型 / LoRA
  data        训练集 / RAG 知识库
  agent       Agent / Skills / 编排流
  tool        MCP 工具 / API / CLI
  credential  API Key / Token / System Prompt
  compute     GPU 集群 / 推理服务

合规边界：
  credential 类型**不存明文**，只存元数据（key_id、scope、provider）；
  真实凭据走密钥管理（Vault / 环境变量）。本模块 schema 层就禁止
  details 出现 plaintext 键。
"""
from __future__ import annotations

import enum
import uuid as uuidlib
from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy import (
    JSON, Column, DateTime, Enum, ForeignKey, Index, String, Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Session, relationship

from app.models.base import Base


class AIAssetKind(str, enum.Enum):
    MODEL = "model"
    DATA = "data"
    AGENT = "agent"
    TOOL = "tool"
    CREDENTIAL = "credential"
    COMPUTE = "compute"


class AIAssetStatus(str, enum.Enum):
    REGISTERED = "registered"   # 已登记
    SHADOW = "shadow"           # 影子 AI（未经审批发现）
    SANCTIONED = "sanctioned"   # 已批准
    DECOMMISSIONED = "decommissioned"  # 已下线


class AIAssetRisk(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AIAsset(Base):
    """AI 资产（六类共用）。"""
    __tablename__ = "soc_ai_assets"

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=func.gen_random_uuid())

    kind = Column(sa.Enum(AIAssetKind, name="ai_asset_kind",
                           values_callable=lambda x: [e.value for e in x]),
                  nullable=False, index=True)
    name = Column(String(200), nullable=False, index=True)
    provider = Column(String(100))          # openai/anthropic/internal/...
    version = Column(String(64))            # 模型版本 / 工具版本

    # 归属（可空：影子 AI 可能尚未确认归属）
    owner = Column(String(255))             # 责任人用户名/邮箱
    business_unit = Column(String(100))
    business_system_id = Column(
        UUID(as_uuid=True),
        ForeignKey("soc_business_systems.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    status = Column(sa.Enum(AIAssetStatus, name="ai_asset_status",
                            values_callable=lambda x: [e.value for e in x]),
                    nullable=False, default=AIAssetStatus.REGISTERED,
                    server_default=AIAssetStatus.REGISTERED.value,
                    index=True)
    risk_level = Column(sa.Enum(AIAssetRisk, name="ai_asset_risk",
                               values_callable=lambda x: [e.value for e in x]),
                        nullable=False, default=AIAssetRisk.MEDIUM,
                        server_default=AIAssetRisk.MEDIUM.value)

    # 类型特定字段（key/value 结构随 kind 变）
    details = Column(JSONB, nullable=False, server_default="{}")

    # 影子 AI 发现来源（手动登记 / 流量识别 / 等），便于审计
    discovery_source = Column(String(64), default="manual",
                              server_default="manual", nullable=False)

    description = Column(Text)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now(),
                        onupdate=func.now())

    business_system = relationship("BusinessSystem", lazy="noload")

    __table_args__ = (
        Index("idx_soc_ai_assets_kind_status", "kind", "status"),
    )


# ----- credential 键白名单（合规：details 禁止存凭证明文）-----

# 禁存键（detail 写入前须检查；这些键出现即拒）
_CREDENTIAL_FORBIDDEN_KEYS = {
    "api_key", "secret", "token", "password", "passwd",
    "private_key", "system_prompt",
}
