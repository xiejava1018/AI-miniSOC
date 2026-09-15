"""
BusinessSystem Schemas（业务系统 CRUD · 治本版 2026-09-14）

第一性原理（ISO 27005 / NIST SP 800-30 / 等保 2.0）：
  业务系统重要性拆为 3 个独立维度：
    - business_impact    业务影响 5 档 core/important/normal/auxiliary/ignorable
    - data_sensitivity   数据敏感度 5 档 extreme/high/medium/low/negligible
    - protection_level   等保等级 5 档 level_5~level_1
  旧 criticality 字段保留为 deprecated read-only alias（写时自动从 data_sensitivity 派生）

详见 app/core/criticality.py 与 docs/design/2026-09-14-asset-criticality-three-dimensions.md。
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List
from datetime import datetime
import re

from app.core.criticality import (
    BUSINESS_IMPACT_VALUES, DATA_SENSITIVITY_VALUES, PROTECTION_LEVEL_VALUES,
    is_valid_protection_level_combination,
)


# code 限制：英文/数字/中划线下划线，便于作资源标识与菜单 path 派生
_CODE_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{1,49}$")


class BusinessSystemBase(BaseModel):
    """业务系统基础字段（Create/Update 共享校验）"""
    code: str = Field(..., min_length=2, max_length=50,
                      description="业务系统唯一编码（小写英文/数字/-/_，如 soc-platform）")
    name: str = Field(..., min_length=2, max_length=100, description="业务系统中文名")
    # === 治本方案：三维度重要性 ===
    business_impact: str = Field(
        "normal",
        description=f"业务影响 5 档：{list(BUSINESS_IMPACT_VALUES)}",
    )
    data_sensitivity: str = Field(
        "medium",
        description=f"数据敏感度 5 档：{list(DATA_SENSITIVITY_VALUES)}",
    )
    protection_level: str = Field(
        "level_2",
        description=f"等保等级 5 档：{list(PROTECTION_LEVEL_VALUES)}",
    )
    # criticality：DEPRECATED（6 个月过渡期）。写入仍接受但不独立存；API 层自动从 data_sensitivity 派生。
    criticality: Optional[str] = Field(
        None,
        description="DEPRECATED: 兼容垫片，写入仅审计保留，不进评分/筛选。",
    )
    # v1.1：责任人改为自由文本（责任人可能不是 SOC 平台用户），部门仍用 FK 下拉
    department_id: Optional[int] = Field(None, description="部门 soc_departments.id")
    owner: Optional[str] = Field(None, max_length=255, description="责任人姓名（自由文本）")
    owner_contact: Optional[str] = Field(None, max_length=50, description="责任人联系电话")
    owner_id: Optional[int] = Field(None, description="平台用户 soc_users.id（可选）")
    description: Optional[str] = Field(None, max_length=2000)

    @field_validator("code")
    @classmethod
    def _code_format(cls, v: str) -> str:
        if not _CODE_RE.match(v):
            raise ValueError("code 必须以字母开头，仅含字母数字中划线下划线，长度 2~50")
        return v.lower()

    @field_validator("business_impact")
    @classmethod
    def _business_impact_enum(cls, v: str) -> str:
        if v not in BUSINESS_IMPACT_VALUES:
            raise ValueError(f"business_impact 必须为 {list(BUSINESS_IMPACT_VALUES)} 之一")
        return v

    @field_validator("data_sensitivity")
    @classmethod
    def _data_sensitivity_enum(cls, v: str) -> str:
        if v not in DATA_SENSITIVITY_VALUES:
            raise ValueError(f"data_sensitivity 必须为 {list(DATA_SENSITIVITY_VALUES)} 之一")
        return v

    @field_validator("protection_level")
    @classmethod
    def _protection_level_enum(cls, v: str) -> str:
        if v not in PROTECTION_LEVEL_VALUES:
            raise ValueError(f"protection_level 必须为 {list(PROTECTION_LEVEL_VALUES)} 之一")
        return v

    @model_validator(mode="after")
    def _three_dimensions_combination(self):
        """三维度联动校验：等保等级 vs BIA/CIA。
        兼容模式：只给了 criticality（未给三维度）时，从 criticality 自动推导。
        """
        from app.core.criticality import LEGACY_CRITICALITY_MAP
        # 兼容垫片：只传 criticality 自动推导三维度
        if self.criticality and (
            self.business_impact == "normal" and self.data_sensitivity == "medium" and self.protection_level == "level_2"
        ):
            mapping = LEGACY_CRITICALITY_MAP.get(self.criticality)
            if mapping:
                self.business_impact = mapping["business_impact"]
                self.data_sensitivity = mapping["data_sensitivity"]
                self.protection_level = mapping["protection_level"]

        ok, msg = is_valid_protection_level_combination(
            self.protection_level, self.business_impact, self.data_sensitivity,
        )
        if not ok:
            raise ValueError(msg)
        return self


class BusinessSystemCreate(BusinessSystemBase):
    """创建业务系统"""
    pass


class BusinessSystemUpdate(BaseModel):
    """更新业务系统——所有字段可选（PATCH 语义）"""
    code: Optional[str] = Field(None, min_length=2, max_length=50)
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    business_impact: Optional[str] = None
    data_sensitivity: Optional[str] = None
    protection_level: Optional[str] = None
    criticality: Optional[str] = Field(None, description="DEPRECATED: 兼容垫片，写入仅审计保留")
    department_id: Optional[int] = None
    owner: Optional[str] = Field(None, max_length=255)
    owner_contact: Optional[str] = Field(None, max_length=50)
    owner_id: Optional[int] = None
    description: Optional[str] = Field(None, max_length=2000)

    @field_validator("code")
    @classmethod
    def _code_format(cls, v):
        if v is None:
            return v
        if not _CODE_RE.match(v):
            raise ValueError("code 必须以字母开头，仅含字母数字中划线下划线，长度 2~50")
        return v.lower()

    @field_validator("business_impact")
    @classmethod
    def _business_impact_enum(cls, v):
        if v is None:
            return v
        if v not in BUSINESS_IMPACT_VALUES:
            raise ValueError(f"business_impact 必须为 {list(BUSINESS_IMPACT_VALUES)} 之一")
        return v

    @field_validator("data_sensitivity")
    @classmethod
    def _data_sensitivity_enum(cls, v):
        if v is None:
            return v
        if v not in DATA_SENSITIVITY_VALUES:
            raise ValueError(f"data_sensitivity 必须为 {list(DATA_SENSITIVITY_VALUES)} 之一")
        return v

    @field_validator("protection_level")
    @classmethod
    def _protection_level_enum(cls, v):
        if v is None:
            return v
        if v not in PROTECTION_LEVEL_VALUES:
            raise ValueError(f"protection_level 必须为 {list(PROTECTION_LEVEL_VALUES)} 之一")
        return v

    @model_validator(mode="after")
    def _three_dimensions_combination(self):
        """Update 时三维度联动校验——只在三字段都显式给出时才校验。"""
        # Update 语义下三个字段都是 Optional，必须都给了才校验
        if self.business_impact is None or self.data_sensitivity is None or self.protection_level is None:
            return self
        ok, msg = is_valid_protection_level_combination(
            self.protection_level, self.business_impact, self.data_sensitivity,
        )
        if not ok:
            raise ValueError(msg)
        return self


class BusinessSystemResponse(BaseModel):
    """业务系统响应（含三维度 + criticality 兼容垫片）"""
    id: str = Field(..., description="UUID")
    code: str
    name: str
    # 三维度
    business_impact: str
    data_sensitivity: str
    protection_level: str
    # criticality：deprecated 兼容垫片（读时从 data_sensitivity 派生）
    criticality: str = Field(..., description="DEPRECATED: 兼容垫片，从 data_sensitivity 派生")
    # 关联展示
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    owner_id: Optional[int] = None
    owner: Optional[str] = None
    owner_contact: Optional[str] = None
    asset_count: int = 0
    description: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class BusinessSystemListResponse(BaseModel):
    """业务系统列表分页响应"""
    total: int
    items: List[BusinessSystemResponse]
    page: int
    page_size: int


# ----- 资产-业务系统 关联 -----


class AssetBusinessLinkCreate(BaseModel):
    """为某资产关联一个业务系统"""
    system_id: str = Field(..., description="业务系统 UUID")
    role: Optional[str] = Field(None, max_length=50,
                                description="web/app/db/mq/cache/gateway 等架构角色")


class AssetBusinessLinkResponse(BaseModel):
    """资产-业务系统关联响应"""
    asset_id: str
    system_id: str
    role: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True
