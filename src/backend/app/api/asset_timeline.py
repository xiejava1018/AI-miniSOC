"""资产统一事件时间线 API（P0 联邦查询 REST 暴露）。

GET /api/v1/assets/{asset_id}/timeline
（路由注册于 app/api/__init__.py：prefix="/assets" + 本文件内部 /{asset_id}/timeline）


依赖既有范式（见 graph.py）：async 端点 + ``Depends(get_db)`` 同步 Session +
服务内 ``run_in_executor`` 卸载阻塞调用。资产锚解析处是唯一使用入参 db 的地方，
且为单次同步查询，不跨线程共享会话。
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.asset import Asset
from app.models.user import User
from app.services.federation.schemas import (
    AssetAnchor,
    EventType,
    TimelineEventOut,
    TimelineResponse,
)
from app.services.federation.timeline_service import TimelineService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["资产事件时间线"])


def _parse_dt(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    except Exception:
        return None


@router.get("/{asset_id}/timeline", response_model=TimelineResponse)
async def get_asset_timeline(
    asset_id: str,
    start: Optional[str] = Query(None, description="ISO8601 起始时间"),
    end: Optional[str] = Query(None, description="ISO8601 结束时间"),
    types: Optional[List[str]] = Query(
        None, description="事件类型过滤: alert/log/change/vuln/identity/behavior"
    ),
    limit: int = Query(200, ge=1, le=1000),
    cursor: Optional[str] = Query(None, description="分页游标（上一页末位 ts+event_id 编码）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 解析资产（同步 Session；仅此一处 DB 操作，不跨线程共享）
    try:
        aid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid asset_id")
    asset = db.query(Asset).filter(Asset.id == aid).first()
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    anchor = AssetAnchor.from_asset(asset)

    now = datetime.now(timezone.utc)
    end_dt = _parse_dt(end) or now
    start_dt = _parse_dt(start) or (end_dt - timedelta(days=7))

    type_enums = None
    if types:
        # 兼容两种传参：?types=a&types=b（FastAPI 原生）与 ?types=a,b,c（前端 join(',')）
        flat: List[str] = []
        for t in types:
            flat.extend(x.strip() for x in t.split(",") if x.strip())
        try:
            type_enums = [EventType(t) for t in flat]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"invalid event type in {flat}")

    result = await TimelineService(db).get_timeline(
        anchor=anchor,
        start=start_dt,
        end=end_dt,
        types=type_enums,
        limit=limit,
        cursor=cursor,
    )

    events_out = [
        TimelineEventOut(
            event_id=e.event_id,
            ts=e.ts,
            source=e.source.value,
            event_type=e.event_type.value,
            asset_anchor=e.asset_anchor,
            asset_id=e.asset_id,
            severity=e.severity,
            summary=e.summary,
            payload=e.payload,
            raw_ref=e.raw_ref,
        )
        for e in result.events
    ]

    return TimelineResponse(
        asset_id=result.asset_id,
        events=events_out,
        next_cursor=result.next_cursor,
        source_status=result.source_status,
        coverage_note=result.coverage_note,
    )
