"""Notification Schemas

站内通知相关的请求/响应模型。
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============== Request ==============


class NotificationTestRequest(BaseModel):
    """管理员手动测试通知"""

    title: str = Field(default="测试通知", max_length=200)
    content: str = Field(default="这是一条测试通知", max_length=1000)
    link: Optional[str] = Field(default=None, max_length=500)


# ============== Response ==============


class NotificationOut(BaseModel):
    """单条通知出参"""

    id: UUID
    user_id: int
    type: str
    title: str
    content: Optional[str]
    link: Optional[str]
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """通知列表分页响应"""

    total: int
    items: List[NotificationOut]
    page: int
    page_size: int


class UnreadCountOut(BaseModel):
    """未读数"""

    count: int


class MarkAllReadOut(BaseModel):
    """全标已读影响行数"""

    updated: int
