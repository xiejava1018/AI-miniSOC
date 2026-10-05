"""整改工单 API（OH-4.6 · S10）

路径：/api/v1/assets/remediation/**
  GET  /remediation/tickets             工单列表
  GET  /remediation/tickets/{id}        详情
  POST /remediation/tickets             从来源派单（对账差异 / 合规 fail 项）
  POST /remediation/tickets/{id}/assign 指派责任人
  POST /remediation/tickets/{id}/advance 状态流转

权限（X1）：菜单「整改工单」挂资产管理下，view / assign / advance 三枚
按钮权限（迁移 g3b4c5d6e7f8 种子）；写端点均 @log_audit。
注册顺序：静态两段路径，须在 assets.router（/{asset_id} catch-all）之前。
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
from app.models.asset_reconciliation import AssetReconciliation
from app.models.compliance import ComplianceFinding
from app.models.user import User
from app.services.remediation_workflow import (
    RemediationConflictError,
    RemediationError,
    RemediationWorkflowService,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_uuid(raw: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"{field} 不是合法 UUID") from exc


def _parse_due(due_at: Optional[str]) -> object:
    if not due_at:
        return None
    from datetime import datetime
    try:
        return datetime.fromisoformat(due_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="due_at 需为 ISO 时间") from exc


@router.get("/remediation/tickets", summary="整改工单列表")
async def list_tickets(
    status: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None, description="reconciliation/compliance"),
    assignee: Optional[str] = Query(None),
    asset_id: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_button_permission("remediation", "view")),
):
    svc = RemediationWorkflowService(db)
    aid = _parse_uuid(asset_id, "asset_id") if asset_id else None
    return svc.list_tickets(
        status=status,
        source_type=source_type,
        assignee=assignee,
        asset_id=aid,
        page=page,
        page_size=page_size,
    )


@router.get("/remediation/tickets/{ticket_id}", summary="工单详情")
async def get_ticket(
    ticket_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_button_permission("remediation", "view")),
):
    svc = RemediationWorkflowService(db)
    try:
        return svc.to_dict(svc.get_ticket(_parse_uuid(ticket_id, "ticket_id")))
    except RemediationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/remediation/tickets", summary="从来源派单（对账差异/合规 fail 项）")
@log_audit(action="REMEDIATION_CREATE", resource_type="remediation_ticket")
async def create_ticket(
    payload: dict = Body(
        ...,
        example={
            "source_type": "reconciliation",
            "source_id": "uuid",
            "assignee": "ops",
            "due_at": "2026-10-12T00:00:00Z",
        },
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_button_permission("remediation", "assign")),
):
    source_type = str(payload.get("source_type") or "")
    source_id = payload.get("source_id")
    if source_type not in ("reconciliation", "compliance"):
        raise HTTPException(status_code=400, detail="source_type 只能是 reconciliation/compliance")
    if not source_id:
        raise HTTPException(status_code=400, detail="缺少 source_id")

    sid = _parse_uuid(str(source_id), "source_id")
    due = _parse_due(payload.get("due_at"))
    svc = RemediationWorkflowService(db)

    if source_type == "reconciliation":
        row = db.get(AssetReconciliation, sid)
        if row is None:
            raise HTTPException(status_code=404, detail="对账差异不存在")
        ticket = svc.create_from_reconciliation(
            row,
            created_by=current_user.username,
            assignee=payload.get("assignee"),
            due_at=due,
        )
    else:
        finding = db.get(ComplianceFinding, sid)
        if finding is None:
            raise HTTPException(status_code=404, detail="合规问题项不存在")
        if finding.status != "fail":
            raise HTTPException(status_code=422, detail="只有 fail 项可派整改工单")
        ticket = svc.create_from_compliance_finding(
            finding,
            created_by=current_user.username,
            assignee=payload.get("assignee"),
            due_at=due,
        )
    return svc.to_dict(ticket)


@router.post("/remediation/tickets/{ticket_id}/assign", summary="指派责任人/期限")
@log_audit(action="REMEDIATION_ASSIGN", resource_type="remediation_ticket")
async def assign_ticket(
    ticket_id: str,
    payload: dict = Body(..., example={"assignee": "ops", "due_at": "2026-10-12T00:00:00Z"}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_button_permission("remediation", "assign")),
):
    assignee = str(payload.get("assignee") or "").strip()
    if not assignee:
        raise HTTPException(status_code=400, detail="assignee 不能为空")
    svc = RemediationWorkflowService(db)
    try:
        ticket = svc.assign(
            _parse_uuid(ticket_id, "ticket_id"),
            assignee=assignee,
            due_at=_parse_due(payload.get("due_at")),
            username=current_user.username,
        )
    except RemediationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RemediationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return svc.to_dict(ticket)


@router.post("/remediation/tickets/{ticket_id}/advance", summary="状态流转（含验证）")
@log_audit(action="REMEDIATION_ADVANCE", resource_type="remediation_ticket")
async def advance_ticket(
    ticket_id: str,
    payload: dict = Body(..., example={"to_status": "resolved", "note": "已补录台账"}),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_button_permission("remediation", "advance")),
):
    to_status = str(payload.get("to_status") or "").strip()
    if not to_status:
        raise HTTPException(status_code=400, detail="缺少 to_status")
    svc = RemediationWorkflowService(db)
    try:
        ticket = svc.advance(
            _parse_uuid(ticket_id, "ticket_id"),
            to_status=to_status,
            username=current_user.username,
            note=payload.get("note"),
        )
    except RemediationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RemediationConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return svc.to_dict(ticket)
