"""Role Schemas"""

from pydantic import BaseModel, Field
from typing import Optional


class RoleBase(BaseModel):
    """角色基础模型"""
    name: str = Field(..., min_length=2, max_length=50, description="角色名称")
    code: str = Field(..., min_length=2, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$', description="角色代码")
    description: Optional[str] = Field(None, max_length=500, description="描述")


class RoleCreate(RoleBase):
    """创建角色"""
    is_active: bool = Field(default=True, description="是否激活")


class RoleUpdate(BaseModel):
    """更新角色"""
    name: Optional[str] = Field(None, min_length=2, max_length=50, description="角色名称")
    code: Optional[str] = Field(None, min_length=2, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$', description="角色代码")
    description: Optional[str] = Field(None, max_length=500, description="描述")
    is_active: Optional[bool] = Field(None, description="是否激活")


class RoleResponse(RoleBase):
    """角色响应"""
    id: int = Field(..., description="角色ID")
    is_active: bool = Field(..., description="是否激活")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class RoleMenusUpdate(BaseModel):
    """更新角色菜单权限"""
    menu_ids: list[int] = Field(..., description="菜单ID列表")


class RoleWithMenusResponse(RoleResponse):
    """角色及菜单权限响应"""
    menu_ids: list[int] = Field(default_factory=list, description="菜单ID列表")
    permissions: list[str] = Field(default_factory=list, description="权限列表")
