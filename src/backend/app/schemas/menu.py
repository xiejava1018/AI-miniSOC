# src/backend/app/schemas/menu.py
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class MenuPermissionItem(BaseModel):
    """菜单按钮权限项"""
    title: str = Field(..., description="权限名称")
    authMark: str = Field(..., description="权限标识")


class MenuBase(BaseModel):
    """菜单基础schema"""
    name: str = Field(max_length=50, description="菜单名称")
    title: Optional[str] = Field(None, max_length=50, description="菜单标题")
    path: str = Field(max_length=200, description="菜单路径")
    icon: Optional[str] = Field(None, max_length=50, description="菜单图标")
    component: Optional[str] = Field(None, max_length=200, description="组件路径")
    sort_order: int = Field(0, description="排序")
    is_visible: bool = Field(True, description="是否可见")
    permissions: list[MenuPermissionItem] = Field(default_factory=list, description="按钮权限列表")


class MenuCreate(MenuBase):
    """创建菜单schema"""
    parent_id: Optional[int] = Field(None, description="父菜单ID")


class MenuUpdate(BaseModel):
    """更新菜单schema"""
    name: Optional[str] = Field(None, max_length=50, description="菜单名称")
    title: Optional[str] = Field(None, max_length=50, description="菜单标题")
    path: Optional[str] = Field(None, max_length=200, description="菜单路径")
    icon: Optional[str] = Field(None, max_length=50, description="菜单图标")
    component: Optional[str] = Field(None, max_length=200, description="组件路径")
    parent_id: Optional[int] = Field(None, description="父菜单ID")
    sort_order: Optional[int] = Field(None, description="排序")
    is_visible: Optional[bool] = Field(None, description="是否可见")
    permissions: Optional[list[MenuPermissionItem]] = Field(None, description="按钮权限列表")


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
