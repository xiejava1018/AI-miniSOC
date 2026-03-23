"""User Schemas"""

from pydantic import BaseModel, EmailStr, Field, field_validator, computed_field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: Optional[EmailStr] = Field(None, description="邮箱")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    department: Optional[str] = Field(None, max_length=100, description="部门")


class UserCreate(UserBase):
    """创建用户"""
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    role_id: Optional[int] = Field(None, description="角色ID")
    is_active: bool = Field(default=True, description="是否激活")


class UserUpdate(BaseModel):
    """更新用户"""
    email: Optional[EmailStr] = Field(None, description="邮箱")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    department: Optional[str] = Field(None, max_length=100, description="部门")
    role_id: Optional[int] = Field(None, description="角色ID")
    is_active: Optional[bool] = Field(None, description="是否激活")


class UserResponse(UserBase):
    """用户响应"""
    id: int = Field(..., description="用户ID")
    role_id: Optional[int] = Field(None, description="角色ID")
    role_name: Optional[str] = Field(None, description="角色名称")
    is_admin: bool = Field(default=False, description="是否管理员")
    status: str = Field(..., description="用户状态")
    last_login: Optional[datetime] = Field(None, description="最后登录时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    @computed_field
    @property
    def is_active(self) -> bool:
        """是否激活"""
        return self.status == "active"

    @computed_field
    @property
    def is_locked(self) -> bool:
        """是否锁定"""
        return self.status == "locked"

    def has_menu_access(self, menu_path: str) -> bool:
        """检查用户是否有指定菜单的访问权限"""
        # 管理员拥有所有权限
        if self.is_admin:
            return True
        # TODO: 实现基于角色的菜单权限检查
        # 当前简化实现：非管理员只返回False
        # 完整实现需要从数据库查询用户的菜单权限
        return False

    class Config:
        from_attributes = True


class UserListResponse(BaseModel):
    """用户列表响应"""
    total: int = Field(..., description="总数")
    items: list[UserResponse] = Field(..., description="用户列表")


class ResetPasswordRequest(BaseModel):
    """重置密码请求"""
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")
    confirm_password: str = Field(..., min_length=6, max_length=100, description="确认密码")


class LockUserRequest(BaseModel):
    """锁定用户请求"""
    is_locked: bool = Field(..., description="是否锁定")
    lock_reason: Optional[str] = Field(None, max_length=500, description="锁定原因")
