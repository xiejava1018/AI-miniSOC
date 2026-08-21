"""资产对账 API（P3 / F1.3）

端点分层与 compliance 一致：
  判定层（无 LLM）：POST /reconcile、GET /reconciliations、PUT .../resolve
  解读层（LLM）  ：GET /reconcile/report

路由注册顺序注意：本文件全部路径为 /assets/reconcile** 或 /assets/reconciliations**
（静态两段），必须在 assets.router 之前注册，否则被 /assets/{asset_id} 抢匹配。
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.permissions import require_button_permission
from app.models.asset_reconciliation import (
    STATUS_PENDING,
    TERMINAL_STATUSES,
    TYPE_MISMATCH,
    TYPE_OFFLINE,
    TYPE_SHADOW,
    AssetReconciliation,
)
from app.models.user import User
from app.services.asset_reconciliation import (
    AssetReconciliationService,
    ReconciliationError,
)
from app.services.reconcile_ai import ReconciliationReportService

logger = logging.getLogger(__name__)
router = APIRouter()

_VALID_TYPES = (TYPE_SHADOW, TYPE_OFFLINE, TYPE_MISMATCH)


def _parse_uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail=f"{label} 格式不正确")


def _out(row: AssetReconciliation) -> dict:
    return {
        "id": str(row.id),
        "run_id": str(row.run_id),
        "task_id": str(row.task_id) if row.task_id else None,
        "asset_id": str(row.asset_id) if row.asset_id else None,
        "reconciliation_type": row.reconciliation_type,
        "details": row.details or {},
        "status": row.status,
        "resolved_by": row.resolved_by,
        "resolved_at": row.resolved_at.isoformat() if row.resolved_at else None,
        "resolve_note": row.resolve_note,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.post("/reconcile", summary="触发资产对账（规则判定，不调 AI）")
async def run_reconcile(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_button_permission("reconciliation", "reconcile")),
):
    """对比台账与 Wazuh Agent 列表。

    Wazuh 不可达时返回 503 而非空结果——把采集故障伪装成"无差异"
    会让运维以为台账是准的，这是 PRD 明令禁止的行为。
    """
    try:
        return AssetReconciliationService(db).run()
    except ReconciliationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/reconcile/summary", summary="最近一次对账摘要（差异分布 + 数据新鲜度）")
async def reconcile_summary(
    run_id: Optional[str] = Query(None, description="指定批次；缺省取最近一次"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rid = _parse_uuid(run_id, "run_id") if run_id else None
    return AssetReconciliationService(db).summary(rid)


@router.get("/reconcile/report", summary="AI 生成对账报告（含数据窗口标注）")
async def reconcile_report(
    run_id: Optional[str] = Query(None),
    force: bool = Query(False, description="无差异时也强制调用 AI（默认省调用）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rid = _parse_uuid(run_id, "run_id") if run_id else None
    return ReconciliationReportService(db).report(rid, force=force)


@router.get("/reconciliations", summary="对账差异列表")
async def list_reconciliations(
    run_id: Optional[str] = Query(None, description="缺省取最近一次对账批次"),
    all_runs: bool = Query(False, description="true 则跨批次查询（历史）"),
    reconciliation_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if reconciliation_type and reconciliation_type not in _VALID_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"reconciliation_type 只能是 {'/'.join(_VALID_TYPES)}",
        )
    if status and status not in (STATUS_PENDING, *TERMINAL_STATUSES):
        raise HTTPException(status_code=400, detail="status 取值不合法")

    svc = AssetReconciliationService(db)
    rid: Optional[uuid.UUID]
    if all_runs:
        rid = None
    elif run_id:
        rid = _parse_uuid(run_id, "run_id")
    else:
        rid = svc.latest_run_id()
        if rid is None:
            return {"total": 0, "page": page, "page_size": page_size, "records": []}

    result = svc.list_diffs(
        run_id=rid,
        recon_type=reconciliation_type,
        status=status,
        page=page,
        page_size=page_size,
    )
    return {
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "records": [_out(r) for r in result["records"]],
    }


@router.put("/reconciliations/{recon_id}/resolve", summary="处理对账差异（状态机 + 审计）")
async def resolve_reconciliation(
    recon_id: str,
    request: Request,
    payload: dict = Body(..., example={"status": "resolved", "note": "已补录台账"}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_button_permission("reconciliation", "resolve")),
):
    """pending → confirmed / ignored / resolved。

    重复处理会返回 409：状态机在服务层用带条件的 UPDATE 保证，
    两个并发请求只有一个能成功。
    """
    rid = _parse_uuid(recon_id, "recon_id")
    status = str(payload.get("status") or "").strip()
    note = payload.get("note")
    if status not in TERMINAL_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"status 只能是 {'/'.join(TERMINAL_STATUSES)}",
        )

    svc = AssetReconciliationService(db)
    try:
        row = svc.resolve(
            recon_id=rid,
            status=status,
            user_id=current_user.id,
            username=current_user.username,
            note=note,
            ip_address=request.client.host if request.client else None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # 重复处理 / 并发抢占 —— 语义是冲突，不是参数错
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _out(row)
