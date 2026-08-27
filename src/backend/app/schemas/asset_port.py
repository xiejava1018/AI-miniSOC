"""
资产端口 Schema
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import uuid


class AssetPortBase(BaseModel):
    """资产端口基础模型"""
    asset_ip: str
    port: int
    protocol: str = "tcp"  # tcp, udp
    state: str = "open"  # open, closed, filtered
    service: Optional[str] = None
    version: Optional[str] = None
    service_banner: Optional[str] = None
    vulnerability: Optional[str] = None


class AssetPortCreate(AssetPortBase):
    """创建端口"""
    asset_id: Optional[str] = None


class AssetPortUpdate(BaseModel):
    """更新端口"""
    state: Optional[str] = None
    service: Optional[str] = None
    version: Optional[str] = None
    service_banner: Optional[str] = None
    vulnerability: Optional[str] = None


class AssetPortResponse(AssetPortBase):
    """端口响应"""
    id: str
    asset_id: Optional[str] = None
    scan_time: datetime
    last_seen: Optional[datetime] = None
    # 多源融合（方案 A）：观测来源清单
    sources: Optional[list] = None
    last_seen_by_source: Optional[dict] = None
    created_at: datetime

    model_config = {
        "from_attributes": True
    }

    @field_validator('id', 'asset_id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        if v is None:
            return None
        if isinstance(v, uuid.UUID):
            return str(v)
        return v


class AssetPortListResponse(BaseModel):
    """端口列表响应"""
    items: list[AssetPortResponse]
    total: int
    skip: int
    limit: int
