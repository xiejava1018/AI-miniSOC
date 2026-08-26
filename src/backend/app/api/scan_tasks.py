"""
扫描任务 + 一键纳管 端点（人类，admin/operator，P3/F-S3）

设计依据：docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md §6.4.1

权限矩阵（X1 扩展）：
  - scan_run          → operator / admin
  - scan_view         → viewer+
  - scan_finding_manage → operator / admin

端点：
  - POST  /scan/run                    建任务（control plane）
  - GET   /scan/tasks                  任务列表
  - GET   /scan/tasks/{uuid}           任务详情
  - POST  /scan/tasks/{uuid}/cancel    取消（拉模型下置 cancelled 状态位）
  - GET   /scan/findings               发现清单
  - POST  /scan/findings/{id}/adopt    一键纳管（写 soc_assets）
  - POST  /scan/findings/{id}/ignore   标记忽略
"""

from __future__ import annotations

import logging
import uuid as uuidlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.permissions import require_role
from app.models.asset import Asset
from app.models.scanner_models import ScanFinding, ScannerTask
from app.models.user import User
# AuditLog 在 app.models.audit_log，不在 asset_reconciliation（CLAUDE.md 教训：手甪 import 路径）

logger = logging.getLogger(__name__)
router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_uuid(value: str, label: str) -> uuidlib.UUID:
    try:
        return uuidlib.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail=f"{label} 格式不正确")


# ============================================================================
# POST /scan/run  建扫描任务（控制面）
# ============================================================================
@router.post("/run")
async def run_scan(
    body: dict = Body(...),
    current_user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    """建一条 ScannerTask pending，由扫描器下次轮询认领。

    body:
      {
        "mode": "internal" | "public" | "ports",
        "targets": "192.168.0.0/24",         # 逗号分隔
        "assign_mode": "auto" | "pinned",
        "target_scanner_id": null,
        "schedule": {"type": "now"|"cron", "cron": "0 3 * * *"},  # 简化：本接口只接 now，cron 走 central_scan_scheduler
        "nmap_args": null,
        "notify": true
      }
    """
    from app.services.central_scan_scheduler import _resolve_targets  # 复用

    mode = body.get("mode", "public")
    if mode not in ("internal", "public", "ports"):
        raise HTTPException(status_code=400, detail=f"invalid mode: {mode}")

    targets_str = body.get("targets", "")
    if not targets_str:
        raise HTTPException(status_code=400, detail="targets 不能为空")
    target_summary = [
        {"type": "cidr" if "/" in t else "ip", "value": t.strip()}
        for t in targets_str.split(",") if t.strip()
    ]

    assign_mode = body.get("assign_mode", "auto")
    if assign_mode not in ("auto", "pinned"):
        raise HTTPException(status_code=400, detail=f"invalid assign_mode: {assign_mode}")
    target_scanner_id = body.get("target_scanner_id")
    if assign_mode == "pinned" and not target_scanner_id:
        raise HTTPException(status_code=400, detail="pinned 必须指定 target_scanner_id")

    nmap_args = body.get("nmap_args")
    notify = body.get("notify", True)
    schedule = body.get("schedule") or {"type": "now"}
    if schedule.get("type") == "cron":
        raise HTTPException(
            status_code=400,
            detail="cron 定时请走 central_scan_scheduler（每天 03:00/04:00 自动），"
                   "本接口仅支持立即执行",
        )

    task = ScannerTask(
        task_uuid=uuidlib.uuid4(),
        mode=mode,
        scope="manual",
        status="pending",
        triggered_by=current_user.username,
        target_summary=target_summary,
        target_scanner_id=target_scanner_id,
        assign_mode=assign_mode,
        capabilities=[mode],
        nmap_args=nmap_args,
        run_reason="manual",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    logger.info(
        "user %s 手动建任务 mode=%s targets=%d assign=%s task_uuid=%s",
        current_user.username, mode, len(target_summary), assign_mode, task.task_uuid,
    )
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "task_uuid": str(task.task_uuid),
            "status": task.status,
            "mode": task.mode,
            "target_count": len(target_summary),
            "assign_mode": task.assign_mode,
            "target_scanner_id": task.target_scanner_id,
            "notify": notify,
            "started_at": task.started_at.isoformat() if task.started_at else None,
        },
    }


# ============================================================================
# GET /scan/tasks  任务列表
# ============================================================================
@router.get("/tasks")
async def list_tasks(
    status: Optional[str] = Query(None, description="pending/running/success/failed/cancelled"),
    mode: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """任务列表（分页 + 过滤）。viewer+ 可看。"""
    q = db.query(ScannerTask)
    if status:
        q = q.filter(ScannerTask.status == status)
    if mode:
        q = q.filter(ScannerTask.mode == mode)
    total = q.count()
    items = q.order_by(ScannerTask.started_at.desc()).offset(skip).limit(limit).all()
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "total": total,
            "items": [
                {
                    "task_uuid": str(t.task_uuid),
                    "mode": t.mode,
                    "scope": t.scope,
                    "status": t.status,
                    "triggered_by": t.triggered_by,
                    "assign_mode": t.assign_mode,
                    "target_scanner_id": t.target_scanner_id,
                    "scanner_id": t.scanner_id,
                    "run_reason": t.run_reason,
                    "started_at": t.started_at.isoformat() if t.started_at else None,
                    "finished_at": t.finished_at.isoformat() if t.finished_at else None,
                    "duration_ms": t.duration_ms,
                    "items_scanned": t.items_scanned,
                    "items_created": t.items_created,
                    "items_updated": t.items_updated,
                    "items_failed": t.items_failed,
                    "error_message": t.error_message,
                    "parent_task_id": str(t.parent_task_id) if t.parent_task_id else None,
                } for t in items
            ],
        },
    }


# ============================================================================
# GET /scan/tasks/{uuid}  任务详情
# ============================================================================
@router.get("/tasks/{task_uuid}")
async def get_task(
    task_uuid: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    uid = _parse_uuid(task_uuid, "task_uuid")
    t = db.query(ScannerTask).filter(ScannerTask.task_uuid == uid).first()
    if not t:
        raise HTTPException(status_code=404, detail="task not found")
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "task_uuid": str(t.task_uuid),
            "mode": t.mode,
            "scope": t.scope,
            "status": t.status,
            "triggered_by": t.triggered_by,
            "target_summary": t.target_summary,
            "assign_mode": t.assign_mode,
            "target_scanner_id": t.target_scanner_id,
            "scanner_id": t.scanner_id,
            "capabilities": t.capabilities,
            "run_reason": t.run_reason,
            "nmap_args": t.nmap_args,
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "finished_at": t.finished_at.isoformat() if t.finished_at else None,
            "claimed_at": t.claimed_at.isoformat() if t.claimed_at else None,
            "duration_ms": t.duration_ms,
            "items_scanned": t.items_scanned,
            "items_created": t.items_created,
            "items_updated": t.items_updated,
            "items_failed": t.items_failed,
            "error_message": t.error_message,
            "parent_task_id": str(t.parent_task_id) if t.parent_task_id else None,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        },
    }


# ============================================================================
# POST /scan/tasks/{uuid}/cancel  取消
# ============================================================================
@router.post("/tasks/{task_uuid}/cancel")
async def cancel_task(
    task_uuid: str,
    current_user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    """取消任务（拉模型下：pending/running → cancelled）。

    注意：running 任务实际中止依赖扫描器下次轮询读到 cancelled 状态。
    """
    uid = _parse_uuid(task_uuid, "task_uuid")
    t = db.query(ScannerTask).filter(ScannerTask.task_uuid == uid).first()
    if not t:
        raise HTTPException(status_code=404, detail="task not found")
    if t.status in ("success", "failed", "cancelled"):
        raise HTTPException(
            status_code=400,
            detail=f"task 已是终态 ({t.status})，不可取消",
        )
    t.status = "cancelled"
    t.finished_at = _utcnow()
    t.error_message = f"cancelled by user {current_user.username}"
    db.commit()
    logger.info("user %s 取消 task %s", current_user.username, t.task_uuid)
    return {"code": 200, "msg": "success", "data": {"task_uuid": task_uuid, "status": "cancelled"}}


# ============================================================================
# GET /scan/findings  发现清单
# ============================================================================
@router.get("/findings")
async def list_findings(
    status: Optional[str] = Query(None, description="new/known/adopted/ignored"),
    exposure: Optional[str] = Query(None, description="internal/public"),
    asset_ip: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发现清单（分页 + 过滤）。viewer+ 可看。"""
    q = db.query(ScanFinding)
    if status:
        q = q.filter(ScanFinding.finding_status == status)
    if exposure:
        q = q.filter(ScanFinding.exposure == exposure)
    if asset_ip:
        q = q.filter(ScanFinding.asset_ip == asset_ip)
    total = q.count()
    items = q.order_by(ScanFinding.last_seen.desc()).offset(skip).limit(limit).all()
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "total": total,
            "items": [
                {
                    "id": f.id,
                    "scan_task_uuid": str(f.scan_task_uuid),
                    "asset_ip": f.asset_ip,
                    "mac_address": f.mac_address,
                    "os_guess": f.os_guess,
                    "exposure": f.exposure,
                    "scanner_id": f.scanner_id,
                    "matched_asset_id": str(f.matched_asset_id) if f.matched_asset_id else None,
                    "finding_status": f.finding_status,
                    "first_seen": f.first_seen.isoformat() if f.first_seen else None,
                    "last_seen": f.last_seen.isoformat() if f.last_seen else None,
                } for f in items
            ],
        },
    }


# ============================================================================
# POST /scan/findings/{id}/adopt  一键纳管
# ============================================================================
@router.post("/findings/{finding_id}/adopt")
async def adopt_finding(
    finding_id: int,
    body: dict = Body(default_factory=dict),
    current_user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    """一键纳管：把 soc_scan_findings 的一条发现转为 soc_assets 正式记录。

    body (可选):
      {
        "asset_name": "内网未命名设备-01",      # 不传则用 os_guess 或 IP 默认
        "criticality": "medium",                # 业务字段，scanner 不自动设
        "owner": "ops-team",
        "business_unit": "ops"
      }

    关键约束（final.md ADR-2）：
      - criticality/owner/business_unit 由请求体显式提供，scanner 不预设
      - finding.finding_status = "adopted"，matched_asset_id = 新资产 id
      - 写审计日志（action="asset_adopt"）
    """
    f = db.query(ScanFinding).filter(ScanFinding.id == finding_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="finding not found")
    if f.finding_status == "adopted":
        raise HTTPException(status_code=400, detail="finding 已被纳管")
    if f.finding_status == "ignored":
        raise HTTPException(status_code=400, detail="finding 已被忽略，请先解禁")
    if f.matched_asset_id:
        # IP 已在台账，直接把 finding 标 adopted 即可（避免重复建）
        f.finding_status = "adopted"
        db.commit()
        return {
            "code": 200,
            "msg": "success",
            "data": {
                "asset_id": str(f.matched_asset_id),
                "finding_status": "adopted",
                "note": "IP 已在台账，仅更新 finding 状态",
            },
        }

    # 新建 Asset（criticality/owner 由请求体显式提供）
    asset = Asset(
        network_segment="default",
        network_zone="other",
        asset_ip=f.asset_ip,
        mac_address=f.mac_address,
        os_name=f.os_guess or "Unknown",
        name=body.get("asset_name") or f"os_guess" or f"discovered-{f.asset_ip}",
        asset_status="online",
        asset_type="server" if f.exposure == "public" else "workstation",
        criticality=body.get("criticality", "medium"),
        owner=body.get("owner"),
        business_unit=body.get("business_unit"),
        data_source="scanner",
        exposure_level=f.exposure,
    )
    db.add(asset)
    db.flush()
    f.matched_asset_id = asset.id
    f.finding_status = "adopted"

    # 审计日志（CLAUDE.md 教训：adopt 属于「关键动作」必须留痕）
    from app.models.audit_log import AuditLog
    audit = AuditLog(
        user_id=current_user.id,
        username=current_user.username,
        action="asset_adopt",
        resource_type="scanner_finding",
        resource_id=f.id,
        resource_name=str(f.asset_ip),
        new_values={
            "asset_id": str(asset.id),
            "asset_name": asset.name,
            "asset_ip": asset.asset_ip,
            "source": "scanner",
            "scanner_id": f.scanner_id,
            "finding_id": f.id,
        },
    )
    db.add(audit)
    db.commit()
    db.refresh(asset)
    logger.info(
        "user %s 纳管 finding %s (asset_id=%s ip=%s)",
        current_user.username, f.id, asset.id, f.asset_ip,
    )
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "asset_id": str(asset.id),
            "finding_status": "adopted",
        },
    }


# ============================================================================
# POST /scan/findings/{id}/ignore  标记忽略
# ============================================================================
@router.post("/findings/{finding_id}/ignore")
async def ignore_finding(
    finding_id: int,
    current_user: User = Depends(require_role("admin", "operator")),
    db: Session = Depends(get_db),
):
    f = db.query(ScanFinding).filter(ScanFinding.id == finding_id).first()
    if not f:
        raise HTTPException(status_code=404, detail="finding not found")
    f.finding_status = "ignored"
    db.commit()
    return {"code": 200, "msg": "success", "data": {"finding_id": finding_id, "finding_status": "ignored"}}