"""资产统一事件时间线（联邦查询 P0）服务包。

包内模块：
- schemas.py        ：跨三源归一化事件模型 + API 响应模型 + 游标编解码
- adapters.py       ：PG / OpenSearch / Loki 三源适配器（同步，自开独立 Session）
- timeline_service.py：async 编排服务（run_in_executor 卸载阻塞 + 超时隔离）

设计依据：docs/design/2026-10-02-统一融合数据底座架构与建设建议.md §5。
G1–G4 关闭：run_in_executor 卸载阻塞 / 锚定 asset_id 反查 IP 集 / 行为画像 asset_id 可空回退 / 纳入 soc_identity_events。
"""
from __future__ import annotations

# 包级别 re-export：让上层调用方用
# `from app.services.federation import TimelineService` 即可（避免强制记子模块路径）
from .adapters import LokiAdapter, OSAdapter, PGAdapter
from .schemas import (
    AssetAnchor,
    EventRecord,
    EventType,
    SourceKey,
    TimelineEventOut,
    TimelineResponse,
    TimelineResult,
    decode_cursor,
    encode_cursor,
)
from .timeline_service import SourceTimeout, TimelineService

__all__ = [
    # 适配器
    "LokiAdapter",
    "OSAdapter",
    "PGAdapter",
    # 编排服务
    "TimelineService",
    "SourceTimeout",
    # 数据模型
    "AssetAnchor",
    "EventRecord",
    "EventType",
    "SourceKey",
    "TimelineEventOut",
    "TimelineResponse",
    "TimelineResult",
    # 游标编解码
    "encode_cursor",
    "decode_cursor",
]