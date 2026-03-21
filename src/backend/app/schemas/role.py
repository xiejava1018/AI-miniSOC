"""Role Schemas"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class RoleBase(BaseModel):
    """角色基础模型"""
    name: str = Field(..., min_length=2, max_length=50, description="角色名称")
    code: str = Field(..., min_length=2, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$', description="角色代码")
    description: Optional[str] = Field(None, max_length=500, description="描述")


class RoleCreate(RoleBase):
    """创建角色"""
    menu_ids: List[int] = Field(default_factory=list, description="关联的菜单ID列表")
    is_active: bool = Field(default=True, description="是否激活")  # 保留现有字段


class RoleUpdate(BaseModel):
    """更新角色"""
    name: Optional[str] = Field(None, min_length=2, max_length=50, description="角色名称")
    description: Optional[str] = Field(None, max_length=500, description="描述")
    menu_ids: Optional[List[int]] = Field(None, description="菜单ID列表")
    is_active: Optional[bool] = Field(None, description="是否激活")  # 保留现有字段
    # 注意: 不包含 code 字段，因为系统角色不能修改代码


class RoleResponse(RoleBase):
    """角色响应"""
    id: int = Field(..., description="角色ID")
    code: str = Field(..., description="角色代码")  # 添加
    is_active: bool = Field(..., description="是否激活")  # 保留现有字段
    is_system: bool = Field(..., description="是否系统角色")  # 新增
    user_count: int = Field(default=0, description="用户数量")  # 新增
    created_at: datetime = Field(..., description="创建时间")  # 修改为datetime类型
    updated_at: datetime = Field(..., description="更新时间")  # 修改为datetime类型

    class Config:
        from_attributes = True


class RoleMenusUpdate(BaseModel):
    """更新角色菜单权限"""
    menu_ids: list[int] = Field(..., description="菜单ID列表")


class RoleWithMenusResponse(RoleResponse):
    """角色及菜单权限响应"""
    menu_ids: list[int] = Field(default_factory=list, description="菜单ID列表")
    permissions: list[str] = Field(default_factory=list, description="权限列表")


class RoleListResponse(BaseModel):
    """角色列表响应"""
    total: int = Field(..., description="总数")
    items: List[RoleResponse] = Field(..., description="角色列表")
    page: int = Field(..., description="页码")
    page_size: int = Field(..., description="每页数量")


class RoleMenusRequest(BaseModel):
    """菜单权限分配请求"""
    menu_ids: List[int] = Field(..., description="菜单ID列表")
