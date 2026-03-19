"""Menu Schemas"""

from pydantic import BaseModel, Field
from typing import Optional


class MenuBase(BaseModel):
    """菜单基础模型"""
    name: str = Field(..., min_length=2, max_length=50, description="菜单名称")
    code: str = Field(..., min_length=2, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$', description="菜单代码")
    type: str = Field(..., pattern=r'^(directory|menu|button)$', description="菜单类型")
    path: Optional[str] = Field(None, max_length=200, description="路由路径")
    component: Optional[str] = Field(None, max_length=200, description="组件路径")
    icon: Optional[str] = Field(None, max_length=100, description="图标")
    sort_order: int = Field(default=0, description="排序")
    is_visible: bool = Field(default=True, description="是否可见")
    is_enabled: bool = Field(default=True, description="是否启用")
    description: Optional[str] = Field(None, max_length=500, description="描述")


class MenuCreate(MenuBase):
    """创建菜单"""
    parent_id: Optional[int] = Field(None, description="父菜单ID")


class MenuUpdate(BaseModel):
    """更新菜单"""
    name: Optional[str] = Field(None, min_length=2, max_length=50, description="菜单名称")
    code: Optional[str] = Field(None, min_length=2, max_length=50, pattern=r'^[a-zA-Z0-9_-]+$', description="菜单代码")
    type: Optional[str] = Field(None, pattern=r'^(directory|menu|button)$', description="菜单类型")
    parent_id: Optional[int] = Field(None, description="父菜单ID")
    path: Optional[str] = Field(None, max_length=200, description="路由路径")
    component: Optional[str] = Field(None, max_length=200, description="组件路径")
    icon: Optional[str] = Field(None, max_length=100, description="图标")
    sort_order: Optional[int] = Field(None, description="排序")
    is_visible: Optional[bool] = Field(None, description="是否可见")
    is_enabled: Optional[bool] = Field(None, description="是否启用")
    description: Optional[str] = Field(None, max_length=500, description="描述")


class MenuResponse(MenuBase):
    """菜单响应"""
    id: int = Field(..., description="菜单ID")
    parent_id: Optional[int] = Field(None, description="父菜单ID")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class MenuTreeResponse(MenuResponse):
    """菜单树响应"""
    children: list['MenuTreeResponse'] = Field(default_factory=list, description="子菜单")

    @classmethod
    def from_menu(cls, menu: MenuResponse, children: list['MenuTreeResponse'] = None) -> 'MenuTreeResponse':
        """从MenuResponse转换为MenuTreeResponse"""
        return cls(
            **menu.model_dump(),
            children=children or []
        )
