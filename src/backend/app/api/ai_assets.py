"""AI 资产管理 API（OH-4.13 · S13 v1）

端点（统一前缀 /api/v1/ai-assets，挂在 assets.router catch-all 之前）：
  POST /ai-assets              创建（admin/operator）
  GET  /ai-assets              列表（filter: kind, status）
  GET  /ai-assets/{id}         详情
  GET  /ai-assets/dashboard    看板计数
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_role
from app.models import AIAssetKind, AIAssetRisk, AIAssetStatus, User
from app.services.ai_asset_service import (
    AIAssetService,
    CredentialPlaintextError,
)

router = APIRouter()


class AIAssetCreate(BaseModel):
    kind: AIAssetKind
    name: str = Field(..., min_length=1, max_length=200)
    provider: Optional[str] = Field(None, max_length=100)
    version: Optional[str] = Field(None, max_length=64)
    owner: Optional[str] = Field(None, max_length=255)
    business_unit: Optional[str] = Field(None, max_length=100)
    business_system_id: Optional[str] = None
    status: AIAssetStatus = AIAssetStatus.REGISTERED
    risk_level: AIAssetRisk = AIAssetRisk.MEDIUM
    details: dict = Field(default_factory=dict)
    description: Optional[str] = None
    discovery_source: str = "manual"


@router.post("/ai-assets", summary="创建 AI 资产")
async def create_ai_asset(
    body: AIAssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator")),
):
    try:
        a = AIAssetService(db).create(
            kind=body.kind, name=body.name, provider=body.provider,
            version=body.version, owner=body.owner,
            business_unit=body.business_unit,
            business_system_id=body.business_system_id,
            status=body.status, risk_level=body.risk_level,
            details=body.details, description=body.description,
            discovery_source=body.discovery_source,
        )
    except CredentialPlaintextError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize(a)


@router.get("/ai-assets", summary="AI 资产列表")
async def list_ai_assets(
    kind: Optional[AIAssetKind] = Query(None),
    status: Optional[AIAssetStatus] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator",
                                              "viewer", "auditor")),
):
    items = AIAssetService(db).list(kind=kind, status=status, limit=limit)
    return {"total": len(items), "items": [_serialize(a) for a in items]}


@router.get("/ai-assets/dashboard", summary="AI 资产看板")
async def ai_asset_dashboard(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator",
                                              "viewer", "auditor")),
):
    return AIAssetService(db).dashboard()


@router.get("/ai-assets/{asset_id}", summary="AI 资产详情")
async def get_ai_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator",
                                              "viewer", "auditor")),
):
    a = AIAssetService(db).get(asset_id)
    if a is None:
        raise HTTPException(status_code=404, detail="AI 资产不存在")
    return _serialize(a)


def _serialize(a) -> dict:
    return {
        "id": str(a.id),
        "kind": a.kind.value,
        "name": a.name,
        "provider": a.provider,
        "version": a.version,
        "owner": a.owner,
        "business_unit": a.business_unit,
        "business_system_id": str(a.business_system_id)
        if a.business_system_id else None,
        "status": a.status.value,
        "risk_level": a.risk_level.value,
        "details": a.details,
        "description": a.description,
        "discovery_source": a.discovery_source,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }
