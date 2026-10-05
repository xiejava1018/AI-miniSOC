"""资产归属确认 API（OH-UI.3 确认工作台）

路径：/api/v1/assets/attribution/**
  GET  /attribution/reviews            待复核列表（默认 pending）
  GET  /attribution/reviews/{id}       详情（观测 + 全候选评分）
  POST /attribution/reviews/{id}/resolve  裁决 merge/create/dismiss

注册顺序：本文件全部为静态两段路径，必须在 assets.router（含
/{asset_id} catch-all）之前注册，否则被抢匹配（与 reconciliation 相同教训）。
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit_decorator import log_audit
from app.core.database import get_db
from app.core.permissions import require_button_permission
from app.models.attribution_review import (
    STATUS_PENDING,
    TERMINAL_STATUSES,
)
from app.models.user import User
from app.services.attribution_service import (
    AttributionConflictError,
    AttributionError,
    AttributionReviewService,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_uuid(raw: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"{field} 不是合法 UUID") from exc


@router.get("/attribution/reviews", summary="归属待复核列表")
async def list_reviews(
    status: str = Query(STATUS_PENDING),
    candidate_asset_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_button_permission("attribution", "view")),
):
    if status not in (STATUS_PENDING, *TERMINAL_STATUSES):
        raise HTTPException(status_code=400, detail="status 取值不合法")

    candidate_id = None
    if candidate_asset_id:
        candidate_id = _parse_uuid(candidate_asset_id, "candidate_asset_id")

    svc = AttributionReviewService(db)
    return svc.list_reviews(
        status=status,
        candidate_asset_id=candidate_id,
        page=page,
        page_size=page_size,
    )


@router.get("/attribution/reviews/{review_id}", summary="归属待复核详情")
async def get_review(
    review_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_button_permission("attribution", "view")),
):
    rid = _parse_uuid(review_id, "review_id")
    svc = AttributionReviewService(db)
    try:
        review = svc.get_review(rid)
    except AttributionError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return svc.detail_dict(review)


@router.post("/attribution/reviews/{review_id}/resolve", summary="裁决归属（合并/新建/忽略）")
@log_audit(action="ATTRIBUTION_RESOLVE", resource_type="attribution_review")
async def resolve_review(
    review_id: str,
    payload: dict = Body(
        ...,
        example={"decision": "merge", "target_asset_id": "uuid", "note": "确认 IP 漂移"},
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_button_permission("attribution", "resolve")),
):
    """pending → merged / created / dismissed（互斥不可逆）。

    并发裁决时服务层状态判定保证一方成功、另一方拿到 409。
    合并目标必须在候选资产范围内，否则 422；候选已被删除时 422。
    """
    rid = _parse_uuid(review_id, "review_id")
    decision = str(payload.get("decision") or "").strip()
    note = payload.get("note")
    target_raw = payload.get("target_asset_id")
    target_id = _parse_uuid(target_raw, "target_asset_id") if target_raw else None

    svc = AttributionReviewService(db)
    try:
        review = svc.resolve(
            rid,
            decision=decision,
            username=current_user.username,
            target_asset_id=target_id,
            note=note,
        )
    except AttributionConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AttributionError as exc:
        # 候选越界 / 候选已删除 —— 语义不可处理实体，422
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return svc.detail_dict(review)
