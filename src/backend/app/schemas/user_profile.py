"""用户中心自助 schema（PR1 Agent B 自有文件）。

契约来源: docs/design/2026-10-12-用户中心重构与MCP-Key管理设计.md §4.1
GET/PUT /users/me · POST /users/me/change-password
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProfileResponse(BaseModel):
    """GET /users/me 完整资料（比 /auth/me 多 role_code/department 等展示字段）"""

    id: int
    username: str
    nick_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None
    gender: Optional[int] = None
    role_code: Optional[str] = None
    role_name: Optional[str] = None
    department_id: Optional[int] = None
    department_name: Optional[str] = None
    status: Optional[str] = None
    last_login: Optional[datetime] = None
    created_at: Optional[datetime] = None


class ChangePasswordRequest(BaseModel):
    """修改自己密码（强度校验在端点内做，保证 422 detail 精确可控）"""

    old_password: str = Field(..., min_length=1, description="当前密码")
    new_password: str = Field(..., description="新密码（≥6 位）")
