"""联邦时间线统一数据模型（P0）。

定义跨三源（PG / OpenSearch / Loki）归一化的事件结构与 API 响应模型。
详见 docs/design/2026-10-02-统一融合数据底座架构与建设建议.md §5.1 / §5.2。
"""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    ALERT = "alert"
    LOG = "log"
    CHANGE = "change"
    VULN = "vuln"
    IDENTITY = "identity"
    BEHAVIOR = "behavior"


class SourceKey(str, Enum):
    PG = "pg"
    OPENSEARCH = "opensearch"
    LOKI = "loki"


class SourceState(str, Enum):
    OK = "ok"
    TIMEOUT = "timeout"
    ERROR = "error"
    EMPTY = "empty"


@dataclass
class AssetAnchor:
    """资产锚：时间线的统一主键 + 已知 IP 集（用于日志/告警反查）。

    G2 关闭：锚定 asset_id，永不从裸 IP 反推资产；
    IP 集用于 Loki/OS 中仅含 IP 的源做反查匹配。
    """

    asset_id: str
    ips: List[str] = field(default_factory=list)

    @classmethod
    def from_asset(cls, asset) -> "AssetAnchor":
        ips = [ip for ip in (asset.asset_ip, getattr(asset, "public_ip", None)) if ip]
        return cls(asset_id=str(asset.id), ips=ips)


@dataclass
class EventRecord:
    event_id: str
    ts: datetime
    source: SourceKey
    event_type: EventType
    asset_anchor: str
    asset_id: Optional[str] = None
    severity: Optional[int] = None
    summary: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    raw_ref: str = ""


@dataclass
class TimelineResult:
    asset_id: str
    events: List[EventRecord]
    next_cursor: Optional[str]
    source_status: Dict[str, str]
    coverage_note: str
    merged_at: datetime = field(default_factory=datetime.now)


# ---- API 响应模型（Pydantic v2）----


class TimelineEventOut(BaseModel):
    event_id: str
    ts: datetime
    source: str
    event_type: str
    asset_anchor: str
    asset_id: Optional[str] = None
    severity: Optional[int] = None
    summary: str = ""
    payload: Dict[str, Any] = Field(default_factory=dict)
    raw_ref: str = ""


class TimelineResponse(BaseModel):
    asset_id: str
    events: List[TimelineEventOut]
    next_cursor: Optional[str] = None
    source_status: Dict[str, str]
    coverage_note: str = ""


def encode_cursor(ts: datetime, event_id: str) -> str:
    raw = json.dumps([ts.isoformat(), event_id], separators=(",", ":"))
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: Optional[str]):
    if not cursor:
        return None
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        ts_iso, event_id = json.loads(raw)
        return datetime.fromisoformat(ts_iso), event_id
    except Exception:
        return None
