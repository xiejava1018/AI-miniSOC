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
from app.core.database import get_db
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
