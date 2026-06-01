"""系统配置 Schemas"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


# value_type 可选值: string / number / boolean / json / password
VALUE_TYPE_OPTIONS = ["string", "number", "boolean", "json", "password"]


class SystemConfigBase(BaseModel):
    category: str = Field(..., min_length=1, max_length=50, description="配置分类")
    key: str = Field(..., min_length=1, max_length=100, description="配置键")
    value: Optional[str] = Field(None, description="配置值")
    value_type: str = Field(default="string", description="值类型: string/number/boolean/json/password")
    is_encrypted: bool = Field(default=False, description="是否加密存储")
    description: Optional[str] = Field(None, description="说明")


class SystemConfigCreate(SystemConfigBase):
    pass


class SystemConfigUpdate(BaseModel):
    category: Optional[str] = Field(None, min_length=1, max_length=50)
    key: Optional[str] = Field(None, min_length=1, max_length=100)
    value: Optional[str] = Field(None, description="配置值（空字符串表示清空）")
    value_type: Optional[str] = Field(None)
    is_encrypted: Optional[bool] = Field(None)
    description: Optional[str] = Field(None)


class SystemConfigResponse(SystemConfigBase):
    id: int
    updated_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SystemConfigListResponse(BaseModel):
    total: int
    items: List[SystemConfigResponse]
    page: int
    page_size: int


class CategoryItem(BaseModel):
    """分类聚合信息"""
    category: str
    count: int
