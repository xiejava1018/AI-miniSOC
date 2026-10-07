"""
通知通道 Pydantic schemas（OH-NOT-F2 · Phase 1）

CLAUDE.md §1.2 一表前缀 + §0/§3.2 schemas/model 分离。

设计要点：
- 密码字段在 schema 层 NEVER 直接暴露
- config_json 用 dict[str, Any] 类型（具体 schema 配置由 email_sender 校验）
- admin / user 两套 schema 分离
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# NotificationChannel
# ============================================================

class NotificationChannelBase(BaseModel):
    """通道基础 schema"""

    code: str = Field(..., min_length=1, max_length=16, description="inbox/email/...")
    name: str = Field(..., min_length=1, max_length=50)
    enabled: bool = True
    config_json: Dict[str, Any] = Field(default_factory=dict)


class NotificationChannelCreate(NotificationChannelBase):
    """admin 创建通道（Phase 1 不开放）"""

    pass


class NotificationChannelUpdate(BaseModel):
    """admin 更新通道（Phase 1：name / enabled / config_json）"""

    name: Optional[str] = Field(None, max_length=50)
    enabled: Optional[bool] = None
    config_json: Optional[Dict[str, Any]] = None


class NotificationChannelOut(NotificationChannelBase):
    """通道出参 — **config_json 屏蔽 password 字段**"""

    id: int
    created_at: datetime
    updated_at: datetime

    # 标记: 返回时把 password 替换为 "***" 配置（脱敏）
    model_config = ConfigDict(from_attributes=True)


# ============================================================
# NotificationDispatchLog（出参，仅 admin 可见）
# ============================================================

class DispatchLogOut(BaseModel):
    id: UUID
    notification_id: Optional[int] = None  # 旧 Notification.id 是 UUID; Phase 1 先用 UUID
    user_id: int
    channel_code: str
    status: str
    error_text: Optional[str] = None
    sent_at: Optional[datetime] = None
    retry_count: int
    next_retry_at: Optional[datetime] = None
    correlation_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DispatchLogListOut(BaseModel):
    """分页查询结果"""

    items: List[DispatchLogOut]
    total: int
    page: int
    page_size: int


# ============================================================
# UserNotificationPreference
# ============================================================

class UserPrefItem(BaseModel):
    """单条偏好"""

    type: str = Field(..., max_length=64)
    channel_code: str = Field(..., max_length=16)
    enabled: bool


class UserPrefListOut(BaseModel):
    """用户自己的所有偏好"""

    items: List[UserPrefItem]


class UserPrefUpdate(BaseModel):
    """更新某 (type, channel) 的偏好"""

    enabled: bool


# ============================================================
# Channel Test（admin 测 SMTP 连接）
# ============================================================

class ChannelTestRequest(BaseModel):
    """admin 触发测邮件请求"""

    to_address: Optional[str] = Field(
        None,
        description="收件邮箱（默认 admin 自己）",
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )


class ChannelTestResult(BaseModel):
    success: bool
    message: str
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    elapsed_ms: int