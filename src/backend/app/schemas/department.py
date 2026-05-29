"""Department Schemas"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class DepartmentBase(BaseModel):
    """部门基础模型"""
    name: str = Field(..., min_length=2, max_length=50, description="部门名称")
    parent_id: Optional[int] = Field(None, description="上级部门ID")
    status: int = Field(default=1, ge=1, le=2, description="状态: 1=启用, 2=禁用")
    sort: int = Field(default=0, ge=0, description="排序")


class DepartmentCreate(DepartmentBase):
    """创建部门"""
    pass


class DepartmentUpdate(BaseModel):
    """更新部门"""
    name: Optional[str] = Field(None, min_length=2, max_length=50, description="部门名称")
    parent_id: Optional[int] = Field(None, description="上级部门ID")
    status: Optional[int] = Field(None, ge=1, le=2, description="状态: 1=启用, 2=禁用")
    sort: Optional[int] = Field(None, ge=0, description="排序")


class DepartmentResponse(DepartmentBase):
    """部门响应"""
    id: int = Field(..., description="部门ID")
    user_count: int = Field(default=0, description="用户数量")
    created_at: Optional[datetime] = Field(None, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")

    class Config:
        from_attributes = True


class DepartmentListResponse(BaseModel):
    """部门列表响应"""
    total: int = Field(..., description="总数")
    items: List[DepartmentResponse] = Field(..., description="部门列表")
    page: int = Field(..., description="页码")
    page_size: int = Field(..., description="每页数量")


class DepartmentTreeNode(BaseModel):
    """部门树节点"""
    id: int = Field(..., description="部门ID")
    parent_id: Optional[int] = Field(None, description="上级部门ID")
    name: str = Field(..., description="部门名称")
    status: int = Field(default=1, description="状态: 1=启用, 2=禁用")
    sort: int = Field(default=0, description="排序")
    user_count: int = Field(default=0, description="用户数量")
    children: Optional[List["DepartmentTreeNode"]] = Field(None, description="子部门")

    class Config:
        from_attributes = True


# 解决递归引用的 forward reference
DepartmentTreeNode.model_rebuild()
