# src/backend/app/schemas/menu.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class MenuBase(BaseModel):
    """菜单基础schema"""
    name: str = Field(max_length=50, description="菜单名称")
    path: str = Field(max_length=200, description="菜单路径")
    icon: Optional[str] = Field(None, max_length=50, description="菜单图标")
    sort_order: int = Field(0, description="排序")
    is_visible: bool = Field(True, description="是否可见")


class MenuResponse(MenuBase):
    """菜单响应schema"""
    id: int
    parent_id: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MenuTreeResponse(MenuResponse):
    """菜单树响应schema"""
    children: List['MenuTreeResponse'] = []

    class Config:
        from_attributes = True


# 重建模型以支持递归类型
MenuTreeResponse.model_rebuild()
