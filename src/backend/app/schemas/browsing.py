"""
行为检测 Schema
"""

from pydantic import BaseModel
from typing import Optional, Any
from datetime import datetime
from uuid import UUID


# ── 事件 ──────────────────────────────────────────

class BrowsingEventResponse(BaseModel):
    id: UUID
    ip: str
    domain: str
    apptype: Optional[str] = None
    score: int
    severity: str
    rule_hits: Any  # JSONB list[dict]
    source_count: int
    window_start: datetime
    window_end: datetime
    status: str
    incident_id: Optional[UUID] = None
    ai_analysis_id: Optional[UUID] = None
    created_at: datetime
    resolved_at: Optional[datetime] = None
    resolution_note: Optional[str] = None

    class Config:
        from_attributes = True


class BrowsingEventListResponse(BaseModel):
    items: list[BrowsingEventResponse]
    total: int
    page: int
    page_size: int


class BrowsingEventUpdate(BaseModel):
    """处置更新"""
    status: Optional[str] = None  # confirmed/false_positive/resolved/ignored
    resolution_note: Optional[str] = None


# ── 黑名单 ────────────────────────────────────────

class BrowsingBlacklistCreate(BaseModel):
    domain: str
    source: str = "manual"
    reason: Optional[str] = None


class BrowsingBlacklistResponse(BaseModel):
    id: int
    domain: str
    source: str
    reason: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class BrowsingBlacklistListResponse(BaseModel):
    items: list[BrowsingBlacklistResponse]
    total: int


# ── 基线 ──────────────────────────────────────────

class BrowsingBaselineResponse(BaseModel):
    id: int
    ip: str
    domain: str
    first_seen: datetime
    last_seen: datetime
    total_count: int

    class Config:
        from_attributes = True


class BrowsingBaselineListResponse(BaseModel):
    items: list[BrowsingBaselineResponse]
    total: int
    page: int
    page_size: int


# ── 统计 / 配置 ───────────────────────────────────

class BrowsingStatsResponse(BaseModel):
    today_total: int
    today_by_severity: dict[str, int]
    today_by_rule: dict[str, int]
    today_by_ip: list[dict[str, Any]]


class BrowsingRuleConfigResponse(BaseModel):
    """规则配置（来自 soc_system_config）"""
    configs: list[dict[str, Any]]


class BrowsingRuleTestRequest(BaseModel):
    """规则试运行（回放指定窗口，不入库）"""
    minutes: int = 60  # 回放最近 N 分钟


class BrowsingRuleTestResponse(BaseModel):
    findings: list[dict[str, Any]]
    stats: dict[str, Any]
