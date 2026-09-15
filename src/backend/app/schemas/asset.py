"""
资产 Schema（治本版 · 2026-09-14）

第一性原理：资产重要性拆为 3 个独立维度（业务影响 BIA + 数据敏感度 CIA + 等保等级）。
详见 app/core/criticality.py。
"""

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional
from datetime import datetime, date
import uuid

from app.core.criticality import (
    BUSINESS_IMPACT_VALUES, DATA_SENSITIVITY_VALUES, PROTECTION_LEVEL_VALUES,
    is_valid_protection_level_combination,
)


class AssetBase(BaseModel):
    """资产基础模型"""
    name: Optional[str] = None
    network_segment: str = "default"
    network_zone: Optional[str] = "other"
    asset_ip: str
    # 公网 IP（可空）：互联网暴露面扫描目标；云上资产 asset_ip 是内网 IP
    public_ip: Optional[str] = None
    asset_type: Optional[str] = "other"
    # === 治本方案：三维度重要性 ===
    business_impact: Optional[str] = Field(
        "normal",
        description=f"业务影响 5 档：{list(BUSINESS_IMPACT_VALUES)}",
    )
    data_sensitivity: Optional[str] = Field(
        "medium",
        description=f"数据敏感度 5 档，进风险评分：{list(DATA_SENSITIVITY_VALUES)}",
    )
    protection_level: Optional[str] = Field(
        "level_2",
        description=f"等保等级 5 档：{list(PROTECTION_LEVEL_VALUES)}",
    )
    # criticality：DEPRECATED（6 个月过渡期）。写入仍接受但不再驱动任何逻辑。
    criticality: Optional[str] = Field(
        None,
        description="DEPRECATED: 改用三维度。写入时仅审计保留，不进评分/筛选。",
    )
    owner: Optional[str] = None
    business_unit: Optional[str] = None
    asset_description: Optional[str] = None
    mac_address: Optional[str] = None
    wazuh_agent_id: Optional[str] = None
    asset_status: Optional[str] = None
    data_classification: Optional[str] = "internal"
    owner_contact: Optional[str] = None
    data_source: Optional[str] = "manual"
    os_name: Optional[str] = None
    os_version: Optional[str] = None

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
        """三维度联动校验：等保等级 vs BIA/CIA。
        兼容垫片：只传 criticality（未传三维度）时从 criticality 自动推导。
        """
        from app.core.criticality import LEGACY_CRITICALITY_MAP
        # 兼容垫片：只传 criticality 且三维度为默认时自动推导
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


class AssetCreate(AssetBase):
    """创建资产"""
    # P3/F3.2：生命周期（新建时可选录入；EOL 由参考表自动匹配，不在此录入）
    purchase_date: Optional[date] = None
    warranty_end: Optional[date] = None
    # v1 (§7.2.5 F10)：可创建时直接指派责任人与部门
    # owner_id: Integer FK soc_users.id；department_id: BigInteger FK soc_departments.id
    # 取值限参考对应主表；后端 API 侧验证时退化为"裸设"创表后再校正
    owner_id: Optional[int] = None
    department_id: Optional[int] = None


class AssetUpdate(BaseModel):
    """更新资产"""
    name: Optional[str] = None
    network_segment: Optional[str] = None
    network_zone: Optional[str] = None
    asset_type: Optional[str] = None
    # === 治本方案：三维度重要性（Update 语义下全部 Optional）===
    business_impact: Optional[str] = None
    data_sensitivity: Optional[str] = None
    protection_level: Optional[str] = None
    # criticality：DEPRECATED，写入仅审计保留
    criticality: Optional[str] = None
    owner: Optional[str] = None
    business_unit: Optional[str] = None
    asset_description: Optional[str] = None
    asset_status: Optional[str] = None
    wazuh_agent_id: Optional[str] = None
    data_classification: Optional[str] = None
    owner_contact: Optional[str] = None
    # P3/F3.2：生命周期（EOL 走专用覆盖接口 PUT /assets/{id}/eol，不走通用编辑）
    purchase_date: Optional[date] = None
    warranty_end: Optional[date] = None
    public_ip: Optional[str] = None
    # v1 (§7.2.5 F10)：人工校正归属用外键；UI 层负责同时显示 owner 字符串（向后兼容）
    # 不接 business_system_ids：业务系统归属走独立 API（POST /business-systems/assets/{id}/systems）
    # 与确认工作台（F4-F6）单边顺序；不同写入入口会让 hint 中错位。
    owner_id: Optional[int] = None
    department_id: Optional[int] = None

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
        """Update 三维度联动校验——三字段都给时才校验（PATCH 语义）。"""
        if self.business_impact is None or self.data_sensitivity is None or self.protection_level is None:
            return self
        ok, msg = is_valid_protection_level_combination(
            self.protection_level, self.business_impact, self.data_sensitivity,
        )
        if not ok:
            raise ValueError(msg)
        return self


class AssetResponse(AssetBase):
    """资产响应"""
    id: str
    created_at: datetime
    updated_at: datetime
    status_updated_at: Optional[datetime] = None
    parent_id: Optional[str] = None
    # P3/F1.1：风险评分（列表页“风险分”列；None = N/A 未评分/数据不足）
    risk_score: Optional[int] = None
    risk_scored_at: Optional[datetime] = None
    # P3/F3.2：生命周期（详情页展示；expected_eol_source: preset=参考表匹配 / manual=人工指定）
    purchase_date: Optional[date] = None
    warranty_end: Optional[date] = None
    expected_eol: Optional[date] = None
    expected_eol_source: Optional[str] = None
    # v1 (§7.2.5 F10)：归属外键（只读展示，修正走 PUT /assets/{id} + owner_id）
    owner_id: Optional[int] = None
    department_id: Optional[int] = None
    # 业务系统名称列表（用走后取，仅供详情页展示用；不作为必填重复的输入口径）
    business_system_names: Optional[list[str]] = None
    # criticality：DEPRECATED 兼容垫片（API 序列化时由 to_response 钩子从 data_sensitivity 派生，
    # 6 个月内外部脚本可继续读；前端建议改用三维度字段）

    model_config = {
        "from_attributes": True
    }

    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        if isinstance(v, uuid.UUID):
            return str(v)
        return v


class AssetListResponse(BaseModel):
    """资产列表响应"""
    items: list[AssetResponse]
    total: int
    skip: int
    limit: int
