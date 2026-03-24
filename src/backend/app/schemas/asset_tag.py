"""
资产标签 Schema
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import uuid


class AssetTagBase(BaseModel):
    """资产标签基础模型"""
    tag_key: str = Field(..., description="标签键", examples=["environment", "business_system"])
    tag_value: str = Field(..., description="标签值", examples=["production", "hr-system"])


class AssetTagCreate(AssetTagBase):
    """创建标签"""
    pass


class AssetTagUpdate(BaseModel):
    """更新标签"""
    tag_value: str


class AssetTagResponse(AssetTagBase):
    """标签响应"""
    id: str
    asset_id: str
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


class AssetTagListResponse(BaseModel):
    """标签列表响应"""
    items: list[AssetTagResponse]
    total: int
    skip: int
    limit: int


# 常用标签定义
COMMON_TAG_KEYS = {
    "environment": ["production", "staging", "development", "testing"],
    "business_system": ["hr-system", "finance-system", "crm", "erp", "oa-system"],
    "location": ["beijing", "shanghai", "guangzhou", "shenzhen"],
    "team": ["backend", "frontend", "devops", "security"],
    "data_classification": ["public", "internal", "confidential", "secret"]
}
