"""User Schemas"""

from pydantic import BaseModel, EmailStr, Field, field_validator, computed_field
from typing import Optional
from datetime import datetime


# 状态映射：前端数字 -> 后端字符串
_STATUS_TO_BACKEND = {1: "active", 2: "disabled"}
# 状态映射：后端字符串 -> 前端数字
_STATUS_TO_FRONTEND = {"active": 1, "locked": 2, "disabled": 2}


class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: Optional[EmailStr] = Field(None, description="邮箱")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")
    nick_name: Optional[str] = Field(None, max_length=100, description="昵称")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    avatar: Optional[str] = Field(None, max_length=255, description="头像URL")
    gender: Optional[int] = Field(None, ge=0, le=2, description="性别: 0=未知, 1=男, 2=女")
    department_id: Optional[int] = Field(None, description="部门ID")


class UserCreate(UserBase):
    """创建用户"""
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    role_id: Optional[int] = Field(None, description="角色ID")
    status: Optional[int] = Field(1, ge=1, le=2, description="状态: 1=启用, 2=禁用")


class UserUpdate(BaseModel):
    """更新用户"""
    email: Optional[EmailStr] = Field(None, description="邮箱")
    full_name: Optional[str] = Field(None, max_length=100, description="全名")
    nick_name: Optional[str] = Field(None, max_length=100, description="昵称")
    phone: Optional[str] = Field(None, max_length=20, description="手机号")
    avatar: Optional[str] = Field(None, max_length=255, description="头像URL")
    gender: Optional[int] = Field(None, ge=0, le=2, description="性别: 0=未知, 1=男, 2=女")
    department_id: Optional[int] = Field(None, description="部门ID")
    role_id: Optional[int] = Field(None, description="角色ID")
    status: Optional[int] = Field(None, ge=1, le=2, description="状态: 1=启用, 2=禁用")


class UserResponse(BaseModel):
    """用户响应"""
    id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    email: Optional[str] = Field(None, description="邮箱")
    full_name: Optional[str] = Field(None, description="全名")
    nick_name: Optional[str] = Field(None, description="昵称")
    phone: Optional[str] = Field(None, description="手机号")
    avatar: Optional[str] = Field(None, description="头像URL")
    gender: Optional[int] = Field(None, description="性别: 0=未知, 1=男, 2=女")
    department_id: Optional[int] = Field(None, description="部门ID")
    department_name: Optional[str] = Field(None, description="部门名称")
    role_id: Optional[int] = Field(None, description="角色ID")
    role_name: Optional[str] = Field(None, description="角色名称")
    is_admin: bool = Field(default=False, description="是否管理员")
    status: int = Field(..., description="状态: 1=启用, 2=禁用")
    last_login: Optional[datetime] = Field(None, description="最后登录时间")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    @field_validator('status', mode='before')
    @classmethod
    def convert_status_out(cls, v):
        """将后端字符串状态转换为前端数字状态"""
        if isinstance(v, str):
            return _STATUS_TO_FRONTEND.get(v, 1)
        return v

    @field_validator('department_name', mode='before')
    @classmethod
    def extract_department_name(cls, v, info):
        """从 department 关系中提取部门名称"""
        if v:
            return v
        # 尝试从上下文数据中获取
        data = info.data
        if 'department' in data and data['department']:
            dept = data['department']
            return getattr(dept, 'name', None)
        return None

    @field_validator('role_name', mode='before')
    @classmethod
    def extract_role_name(cls, v, info):
        """从 role 关系中提取角色名称"""
        if v:
            return v
        data = info.data
        if 'role' in data and data['role']:
            role = data['role']
            return getattr(role, 'name', None)
        return None

    @computed_field
    @property
    def is_active(self) -> bool:
        """是否激活"""
        return self.status == 1

    @computed_field
    @property
    def is_locked(self) -> bool:
        """是否锁定"""
        # 前端只区分启用/禁用，锁定显示为禁用
        return self.status == 2

    def has_menu_access(self, menu_path: str) -> bool:
        """检查用户是否有指定菜单的访问权限"""
        # 管理员拥有所有权限
        if self.is_admin:
            return True
        # TODO: 实现基于角色的菜单权限检查
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
