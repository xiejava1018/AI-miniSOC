"""
资产 Schema
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class AssetBase(BaseModel):
    """资产基础模型"""
    name: Optional[str] = None
    asset_ip: str
    asset_type: str = "other"
    criticality: str = "medium"
    owner: Optional[str] = None
    business_unit: Optional[str] = None
    asset_description: Optional[str] = None
    mac_address: Optional[str] = None
    wazuh_agent_id: Optional[str] = None
    asset_status: Optional[str] = None


class AssetCreate(AssetBase):
    """创建资产"""
    pass


class AssetUpdate(BaseModel):
    """更新资产"""
    name: Optional[str] = None
    asset_type: Optional[str] = None
    criticality: Optional[str] = None
    owner: Optional[str] = None
    business_unit: Optional[str] = None
    asset_description: Optional[str] = None
    asset_status: Optional[str] = None
    wazuh_agent_id: Optional[str] = None


class AssetResponse(AssetBase):
    """资产响应"""
    id: str = Field(..., alias="id")
    created_at: datetime
    updated_at: datetime
    status_updated_at: Optional[datetime] = None
    parent_id: Optional[str] = None

    class Config:
        from_attributes = True
        # UUID 自动转换为字符串
        populate_by_name = True

    @classmethod
    def from_orm(cls, obj):
        """从 ORM 模型创建"""
        data = {
            "id": str(obj.id),
            "name": obj.name,
            "asset_ip": obj.asset_ip,
            "asset_type": obj.asset_type,
            "criticality": obj.criticality,
            "owner": obj.owner,
            "business_unit": obj.business_unit,
            "asset_description": obj.asset_description,
            "mac_address": str(obj.mac_address) if obj.mac_address else None,
            "wazuh_agent_id": obj.wazuh_agent_id,
            "asset_status": obj.asset_status,
            "created_at": obj.created_at,
            "updated_at": obj.updated_at,
            "status_updated_at": obj.status_updated_at,
            "parent_id": obj.parent_id,
        }
        return cls(**data)


class AssetListResponse(BaseModel):
    """资产列表响应"""
    items: list[AssetResponse]
    total: int
    skip: int
    limit: int
