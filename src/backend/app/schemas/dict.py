"""字典 Schemas"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class DictBase(BaseModel):
    """字典基础模型"""
    dict_type: str = Field(..., min_length=1, max_length=50, description="字典类型")
    dict_code: str = Field(..., min_length=1, max_length=50, description="字典编码")
    dict_label: str = Field(..., min_length=1, max_length=100, description="字典标签")
    color: Optional[str] = Field(None, max_length=20, description="标签颜色")
    sort_order: int = Field(default=0, ge=0, description="排序")
    is_active: bool = Field(default=True, description="是否启用")
    is_default: bool = Field(default=False, description="是否默认值")
    remark: Optional[str] = Field(None, description="备注")


class DictCreate(DictBase):
    """创建字典"""
    pass


class DictUpdate(BaseModel):
    """更新字典"""
    dict_type: Optional[str] = Field(None, min_length=1, max_length=50, description="字典类型")
    dict_code: Optional[str] = Field(None, min_length=1, max_length=50, description="字典编码")
    dict_label: Optional[str] = Field(None, min_length=1, max_length=100, description="字典标签")
    color: Optional[str] = Field(None, max_length=20, description="标签颜色")
    sort_order: Optional[int] = Field(None, ge=0, description="排序")
    is_active: Optional[bool] = Field(None, description="是否启用")
    is_default: Optional[bool] = Field(None, description="是否默认值")
    remark: Optional[str] = Field(None, description="备注")


class DictResponse(DictBase):
    """字典响应"""
    id: int = Field(..., description="字典ID")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")

    class Config:
        from_attributes = True


class DictListResponse(BaseModel):
    """字典列表响应"""
    total: int = Field(..., description="总数")
    items: List[DictResponse] = Field(..., description="字典列表")
    page: int = Field(..., description="页码")
    page_size: int = Field(..., description="每页数量")
