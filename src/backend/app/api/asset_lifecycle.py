"""
资产生命周期 API（PRD F3.2 / v1.2.1）

- GET    /assets/lifecycle/overview        总览（EOL 已超期/30天/90天 + 保修临期，退役建议列表）
- POST   /assets/lifecycle/refresh-eol     按参考表批量回填 EOL（admin；manual 覆盖不触碰）
- GET    /assets/lifecycle/eol-reference   EOL 参考表（admin 维护视角）
- PUT    /assets/{id}/eol                  手动覆盖 EOL 日期（审计；PRD X1：admin/operator）
- DELETE /assets/{id}/eol                  恢复自动匹配（审计）

注册顺序：必须在 assets.router 之前（GET /lifecycle/overview 单段会被
/assets/{asset_id} 抢匹配——与 asset_query/asset_risk 同因）。
"""
import logging
import uuid
from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import User
from app.models.eol_reference import EolReference
from app.services.asset_lifecycle import AssetLifecycleService

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_asset_id(asset_id: str):
    try:
        return uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="资产 ID 格式错误")


def _parse_date(v: str) -> date_type:
    try:
        return date_type.fromisoformat(v)
    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式错误（需 YYYY-MM-DD）")


def _require_admin(current_user: User) -> None:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")


@router.get("/lifecycle/overview")
def lifecycle_overview(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """生命周期总览：退役/升级建议（EOL 已超期 → 30 天 → 90 天 + 保修临期）"""
    return AssetLifecycleService(db).overview()


@router.post("/lifecycle/refresh-eol")
def refresh_eol(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """按 EOL 参考表批量回填（manual 覆盖不触碰；无匹配清空旧 preset 值）"""
    stats = AssetLifecycleService(db).refresh_eol_all()
    return {"message": "EOL 匹配刷新完成", "stats": stats}


@router.get("/lifecycle/eol-reference")
def list_eol_reference(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """EOL 参考表全量（预置 + 人工维护条目；匹配口径见 pattern）"""
    rows = (
        db.query(EolReference)
        .order_by(EolReference.eol_date.asc())
        .all()
    )
    return {"items": [
        {"id": str(r.id), "pattern": r.pattern, "display_name": r.display_name,
         "eol_date": r.eol_date.isoformat(), "source": r.source,
         "notes": r.notes, "enabled": r.enabled}
        for r in rows
    ]}


class EolOverrideRequest(BaseModel):
    eol_date: str  # YYYY-MM-DD


@router.put("/{asset_id}/eol")
def override_eol(
    asset_id: str,
    body: EolOverrideRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """手动覆盖 EOL（优先于参考表；落审计）。PRD 防幻觉设计：人工确认优先。"""
    eol = _parse_date(body.eol_date)
    asset = AssetLifecycleService(db).set_eol_override(_parse_asset_id(asset_id), eol, current_user)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    return {
        "message": "EOL 已设置为人工指定",
        "expected_eol": asset.expected_eol.isoformat(),
        "expected_eol_source": "manual",
    }


@router.delete("/{asset_id}/eol")
def clear_eol(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """恢复自动匹配（立即按参考表重算；落审计）"""
    asset = AssetLifecycleService(db).clear_eol_override(_parse_asset_id(asset_id), current_user)
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    return {
        "message": "已恢复自动匹配",
        "expected_eol": asset.expected_eol.isoformat() if asset.expected_eol else None,
        "expected_eol_source": "preset",
    }
