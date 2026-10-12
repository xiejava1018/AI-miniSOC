"""
MCP Key Schemas（PR1 用户中心重构 + MCP Key 管理）

设计文档：docs/design/2026-10-12-用户中心重构与MCP-Key管理设计.md §4.2

注意：MCPKeyCreatedResponse.key 是明文的**唯一一次**出现——
生成响应之后，任何接口/日志/审计不再返回明文（库里只有哈希）。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MCPKeyCreate(BaseModel):
    """申请新 Key"""
    name: str = Field(..., min_length=1, max_length=50, description="用途标识，如 workbuddy / 我的Claude")
    validity_days: int = Field(..., gt=0, description="有效期（天），上限见配置 mcp.key.max_validity_days")


class MCPKeyExtend(BaseModel):
    """延期"""
    new_validity_days: int = Field(..., gt=0, description="新有效期（天），从现在起算")


class MCPKeyResponse(BaseModel):
    """Key 列表项（无明文）"""
    id: int
    name: str
    key_prefix: str = Field(..., description="如 sk-mcp-Xk9f…（明文前缀，辨认用）")
    status: str = Field(..., description="active / revoked")
    days_remaining: Optional[int] = Field(None, description="剩余天数（revoked 为 None）")
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MCPKeyCreatedResponse(MCPKeyResponse):
    """申请成功响应（含一次性明文）"""
    key: str = Field(..., description="完整 Key 明文——仅此一次返回，请立即保存")


def mcp_key_to_response(row) -> MCPKeyResponse:
    """ORM → Response 的统一转换（days_remaining 运行时计算）。"""
    days_remaining = None
    if row.status == "active" and row.expires_at is not None:
        exp = row.expires_at
        remain = (exp - datetime.utcnow().replace(tzinfo=exp.tzinfo)).total_seconds()
        days_remaining = max(0, int(remain // 86400))
    return MCPKeyResponse(
        id=row.id,
        name=row.name,
        key_prefix=row.key_prefix,
        status=row.status,
        days_remaining=days_remaining,
        expires_at=row.expires_at,
        last_used_at=row.last_used_at,
        created_at=row.created_at,
    )
