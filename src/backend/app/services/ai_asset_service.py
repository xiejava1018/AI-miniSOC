"""AI 资产管理服务（OH-4.13 · S13 v1）

数据底座服务（CRUD + 看板计数），不实现下游场景（影子 AI 发现等独立
任务）。credential 类**禁止 details 存明文**——schema 层校验。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ai_asset import (
    AIAsset,
    AIAssetKind,
    AIAssetRisk,
    AIAssetStatus,
    _CREDENTIAL_FORBIDDEN_KEYS,
)

logger = logging.getLogger(__name__)


class CredentialPlaintextError(ValueError):
    """credential 类型详情含禁存键时抛。"""


def _scrub_credential_details(details: Dict[str, Any]) -> Dict[str, Any]:
    """检查并剔除明文凭据键；保留元数据。"""
    if not isinstance(details, dict):
        return {}
    forbidden = {
        k for k in details
        if k.lower() in _CREDENTIAL_FORBIDDEN_KEYS
    }
    if forbidden:
        raise CredentialPlaintextError(
            f"credential 类型 details 禁止存明文凭据键: {sorted(forbidden)}；"
            "请改为元数据引用（vault/环境变量）"
        )
    return details


class AIAssetService:
    def __init__(self, db: Session):
        self.db = db

    # ---------------- CRUD ----------------

    def create(
        self,
        *,
        kind: AIAssetKind,
        name: str,
        provider: Optional[str] = None,
        version: Optional[str] = None,
        owner: Optional[str] = None,
        business_unit: Optional[str] = None,
        business_system_id: Optional[Any] = None,
        status: AIAssetStatus = AIAssetStatus.REGISTERED,
        risk_level: AIAssetRisk = AIAssetRisk.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
        discovery_source: str = "manual",
    ) -> AIAsset:
        details = details or {}
        if kind == AIAssetKind.CREDENTIAL:
            details = _scrub_credential_details(details)
        asset = AIAsset(
            kind=kind, name=name, provider=provider, version=version,
            owner=owner, business_unit=business_unit,
            business_system_id=business_system_id, status=status,
            risk_level=risk_level, details=details,
            description=description, discovery_source=discovery_source,
        )
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)
        return asset

    def list(
        self,
        *,
        kind: Optional[AIAssetKind] = None,
        status: Optional[AIAssetStatus] = None,
        limit: int = 50,
    ) -> List[AIAsset]:
        q = self.db.query(AIAsset).order_by(AIAsset.created_at.desc())
        if kind is not None:
            q = q.filter(AIAsset.kind == kind)
        if status is not None:
            q = q.filter(AIAsset.status == status)
        return q.limit(limit).all()

    def get(self, asset_id: Any) -> Optional[AIAsset]:
        return self.db.get(AIAsset, asset_id)

    # ---------------- 看板计数 ----------------

    def dashboard(self) -> Dict[str, Any]:
        # 总数 + 按 kind + 按 status + 按 risk
        total = self.db.query(func.count(AIAsset.id)).scalar() or 0
        by_kind = dict(self.db.query(
            AIAsset.kind, func.count(AIAsset.id)
        ).group_by(AIAsset.kind).all())
        by_status = dict(self.db.query(
            AIAsset.status, func.count(AIAsset.id)
        ).group_by(AIAsset.status).all())
        by_risk = dict(self.db.query(
            AIAsset.risk_level, func.count(AIAsset.id)
        ).group_by(AIAsset.risk_level).all())
        # 影子 AI 单独计数（status=shadow + kind=model/data/agent 三类）
        shadow_count = self.db.query(func.count(AIAsset.id)).filter(
            AIAsset.status == AIAssetStatus.SHADOW,
            AIAsset.kind.in_([
                AIAssetKind.MODEL, AIAssetKind.DATA, AIAssetKind.AGENT,
            ])
        ).scalar() or 0
        return {
            "total": total,
            "by_kind": {k.value: v for k, v in by_kind.items()},
            "by_status": {s.value: v for s, v in by_status.items()},
            "by_risk": {r.value: v for r, v in by_risk.items()},
            "shadow_ai_count": shadow_count,
            "red_line": "v1 看板：不含影子 AI 自动识别（独立任务）",
        }
