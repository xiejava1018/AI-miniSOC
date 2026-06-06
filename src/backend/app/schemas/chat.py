"""Chat Schemas

Art Bot 聊天相关的请求/响应模型。
"""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


# ============== Request ==============


class ChatMessageIn(BaseModel):
    """客户端发送的单条消息（首条或多轮追加）"""

    role: str = Field(..., description="user | system", pattern="^(user|system)$")
    content: str = Field(..., min_length=1, max_length=8000)


class ChatCreateRequest(BaseModel):
    """新建会话并发起首轮对话（流式）"""

    message: ChatMessageIn


class ChatContinueRequest(BaseModel):
    """在已有 session 上追加一轮对话（流式）"""

    message: ChatMessageIn


# ============== Response ==============


class ChatMessageOut(BaseModel):
    """单条消息的出参"""

    id: UUID
    role: str
    content: str
    tokens_used: int
    is_truncated: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSessionOut(BaseModel):
    """会话概要出参（列表展示用）"""

    id: UUID
    user_id: int
    title: str
    model_name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatSessionDetailOut(ChatSessionOut):
    """会话详情出参（含消息列表）"""

    messages: List[ChatMessageOut] = Field(default_factory=list)


class ChatSessionListResponse(BaseModel):
    """会话列表分页响应"""

    total: int
    items: List[ChatSessionOut]
    page: int
    page_size: int
