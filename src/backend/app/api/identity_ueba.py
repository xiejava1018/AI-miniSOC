"""行为维 UEBA API（OH-2.8）

路径：/api/v1/assets/ueba/**
  GET /ueba/zombies           僵尸资产候选（S8 前置）
  GET /ueba/{asset_id}        单资产 UEBA 异常评分

注册顺序：静态两段路径，须在 assets.router（/{asset_id} catch-all）之前。
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.audit_decorator import log_audit
from app.core.database import get_db
from app.core.permissions import require_role
from app.models.asset import Asset
from app.models.behavior_profile import BehaviorProfile
from app.models.user import User
from app.services.identity_ueba import detect_zombies, score_behavior_anomaly

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/ueba/zombies", summary="僵尸资产候选（近 N 天零行为+零认证）")
async def zombies(
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return detect_zombies(db, days=days)


@router.post("/ueba/zombies/ticket", summary="僵尸候选派整改工单（人工确认后）")
@log_audit(action="UEBA_ZOMBIE_TICKET", resource_type="remediation_ticket")
async def zombie_ticket(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator")),
):
    """把一个 UEBA 僵尸候选派成整改工单（source_type=ueba_zombie）。

    body: {asset_id, assignee?, due_at?}。同资产未终态工单已存在时只累计 occurrence。
    """
    from datetime import datetime
    from app.services.remediation_workflow import (
        RemediationError,
        RemediationWorkflowService,
    )

    raw = str(payload.get("asset_id") or "")
    try:
        aid = uuid.UUID(raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="asset_id 不是合法 UUID")

    asset = db.get(Asset, aid)
    if asset is None:
        raise HTTPException(status_code=404, detail="资产不存在")

    # 重新跑候选检测取证据（防止用陈旧候选派单）
    scan = detect_zombies(db, days=int(payload.get("days") or 14))
    cand = next(
        (c for c in scan["candidates"] if c["asset_id"] == str(aid)), None,
    )
    if cand is None:
        raise HTTPException(
            status_code=422,
            detail=f"{asset.name or aid} 当前不是僵尸候选（窗口内有活动），不派单",
        )

    due = None
    if payload.get("due_at"):
        try:
            due = datetime.fromisoformat(str(payload["due_at"]).replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail="due_at 需为 ISO 时间")

    svc = RemediationWorkflowService(db)
    try:
        ticket = svc.create_from_zombie(
            asset,
            evidence=cand["evidence"] | {"confidence": cand["confidence"]},
            created_by=current_user.username,
            assignee=payload.get("assignee"),
            due_at=due,
        )
    except RemediationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return svc.to_dict(ticket)


@router.get("/ueba/{asset_id}", summary="单资产 UEBA 行为异常评分")
async def asset_ueba(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        aid = uuid.UUID(str(asset_id))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="asset_id 不是合法 UUID")

    asset = db.get(Asset, aid)
    if asset is None:
        raise HTTPException(status_code=404, detail="资产不存在")

    row = (
        db.query(BehaviorProfile)
        .filter(BehaviorProfile.asset_id == aid)
        .order_by(BehaviorProfile.profile_date.desc())
        .limit(1)
        .first()
    )
    result = score_behavior_anomaly(row, asset_type=asset.asset_type)
    result["asset"] = {
        "id": str(asset.id),
        "name": asset.name,
        "asset_ip": str(asset.asset_ip) if asset.asset_ip else None,
        "asset_type": asset.asset_type,
    }
    result["has_snapshot"] = row is not None
    return result
