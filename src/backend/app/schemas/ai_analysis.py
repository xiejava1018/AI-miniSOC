"""
AI分析 Schema
"""

from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class AIAnalysisBase(BaseModel):
    """AI分析基础模型"""
    alert_id: str
    alert_fingerprint: Optional[str] = None
    explanation: Optional[str] = None
    risk_assessment: Optional[str] = None
    recommendations: Optional[str] = None


class AIAnalysisCreate(AIAnalysisBase):
    """创建AI分析"""
    model_name: str
    model_version: Optional[str] = None
    tokens_used: Optional[int] = None
    cost: Optional[float] = None


class AIAnalysisResponse(AIAnalysisBase):
    """AI分析响应"""
    id: str
    model_name: str
    model_version: Optional[str] = None
    tokens_used: Optional[int] = None
    cost: Optional[float] = None
    created_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True
