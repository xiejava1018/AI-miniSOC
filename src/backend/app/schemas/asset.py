"""
资产 Schema
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, date
import uuid


class AssetBase(BaseModel):
    """资产基础模型"""
    name: Optional[str] = None
    network_segment: str = "default"
    network_zone: Optional[str] = "other"
    asset_ip: str
    asset_type: Optional[str] = "other"
    criticality: Optional[str] = "medium"  # 决策1：四档 critical/high/medium/low（存量 normal 已回填 medium）
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


class AssetCreate(AssetBase):
    """创建资产"""
    # P3/F3.2：生命周期（新建时可选录入；EOL 由参考表自动匹配，不在此录入）
    purchase_date: Optional[date] = None
    warranty_end: Optional[date] = None


class AssetUpdate(BaseModel):
    """更新资产"""
    name: Optional[str] = None
    network_segment: Optional[str] = None
    network_zone: Optional[str] = None
    asset_type: Optional[str] = None
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
