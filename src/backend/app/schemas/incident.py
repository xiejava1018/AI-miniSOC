"""
事件 Schema
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class IncidentBase(BaseModel):
    """事件基础模型"""
    title: str
    description: Optional[str] = None
    severity: str  # critical, high, medium, low
    assigned_to: Optional[str] = None


class IncidentCreate(IncidentBase):
    """创建事件"""
    wazuh_alert_id: Optional[str] = None
    asset_ids: Optional[list[str]] = []


class IncidentUpdate(BaseModel):
    """更新事件"""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None  # open, in_progress, resolved, closed
    severity: Optional[str] = None
    assigned_to: Optional[str] = None
    resolution_notes: Optional[str] = None


class IncidentResponse(IncidentBase):
    """事件响应"""
    id: str
    status: str
    wazuh_alert_id: Optional[str] = None
    created_by: str
    created_at: datetime
    updated_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    ai_analysis_id: Optional[str] = None

    class Config:
        from_attributes = True


class IncidentListResponse(BaseModel):
    """事件列表响应"""
    items: list[IncidentResponse]
    total: int
    skip: int
    limit: int
