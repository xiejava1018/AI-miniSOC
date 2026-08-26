"""
扫描器端点（X-API-Key 鉴权，P3/F-S3 控制面）

设计依据：docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md §7.1

端点清单（4 个）:
  - POST /api/v1/scan/agents/heartbeat  扫描器心跳 upsert 状态
  - GET  /api/v1/scan/tasks/pending       拉取可认领任务（?scanner_id=&caps=）
  - PATCH /api/v1/scan/tasks/{uuid}/claim  原子认领（pending→running）
  - PATCH /api/v1/scan/tasks/{uuid}/report 回写结果（success/failed + counts）

全部端点 require_scanner_api_key。
扫描器**无权**调用人类端点（如 /scan/run）—— 权限边界清晰。
"""

from __future__ import annotations

import logging
import uuid as uuidlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_scanner_api_key
from app.core.database import get_db
from app.models.scanner_models import ScannerAgent, ScannerTask
from app.models.user import User  # noqa: F401  (kept for future ACL hooks)

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
# POST /agents/heartbeat  扫描器心跳 upsert 状态
# ============================================================================
@router.post("/agents/heartbeat")
async def heartbeat(
    body: dict = Body(...),
    scanner: ScannerAgent = Depends(require_scanner_api_key),
    db: Session = Depends(get_db),
):
    """扫描器心跳 — 至少 30s 一次（final.md §4.3 L1）。

    body:
      {
        "ip": "192.168.0.45",                # 可选，心跳时上报
        "version": "1.3.0",                 # 可选
        "capabilities": ["internal","public","ports"],
        "reachable_subnets": ["192.168.0.0/24"],
        "running_tasks": 1
      }
    """
    now = _utcnow()
    scanner.last_heartbeat = now
    scanner.ip = body.get("ip") or scanner.ip
    scanner.version = body.get("version") or scanner.version
    if body.get("capabilities") is not None:
        scanner.capabilities = body["capabilities"]
    if body.get("reachable_subnets") is not None:
        scanner.reachable_subnets = body["reachable_subnets"]
    if body.get("running_tasks") is not None:
        scanner.running_tasks = int(body["running_tasks"])
    scanner.status = "online"
    db.commit()
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "scanner_id": scanner.scanner_id,
            "status": scanner.status,
            "last_heartbeat": now.isoformat(),
        },
    }


# ============================================================================
# GET /tasks/pending  拉取可认领任务
# ============================================================================
@router.get("/tasks/pending")
async def fetch_pending(
    caps: Optional[str] = Query(None, description="逗号分隔的能力，如 internal,public"),
    scanner: ScannerAgent = Depends(require_scanner_api_key),
    db: Session = Depends(get_db),
):
    """拉取可认领任务（pending 状态 + 能力匹配 + 路由匹配）。

    路由逻辑（final.md §7.2 简化版）：
      - target_scanner_id == scanner_id：直接拿
      - target_scanner_id IS NULL 且 capabilities 包含本 scanner 能力：可拿
      - target_scanner_id 指向别的 scanner：跳过
    """
    scanner_caps = set(scanner.capabilities or [])
    if caps:
        scanner_caps.update(c.strip() for c in caps.split(",") if c.strip())

    candidates = (
        db.query(ScannerTask)
        .filter(ScannerTask.status == "pending")
        .all()
    )
    picked: list[dict] = []
    for t in candidates:
        # 路由匹配
        if t.target_scanner_id and t.target_scanner_id != scanner.scanner_id:
            continue
        # 能力匹配（任务所需能力 ∩ 扫描器能力）
        if t.capabilities:
            required = set(t.capabilities or [])
            if not required.issubset(scanner_caps):
                continue
        picked.append({
            "task_uuid": str(t.task_uuid),
            "mode": t.mode,
            "scope": t.scope,
            "nmap_args": t.nmap_args,
            "target_summary": t.target_summary,
            "capabilities": t.capabilities,
            "run_reason": t.run_reason,
        })
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "tasks": picked,
            "scanner_id": scanner.scanner_id,
        },
    }


# ============================================================================
# PATCH /tasks/{uuid}/claim  原子认领
# ============================================================================
@router.patch("/tasks/{task_uuid}/claim")
async def claim_task(
    task_uuid: str,
    scanner: ScannerAgent = Depends(require_scanner_api_key),
    db: Session = Depends(get_db),
):
    """原子认领（pending→running），用 with_for_update 行锁防并发（final.md §7.3）。"""
    uid = _parse_uuid(task_uuid, "task_uuid")
    now = _utcnow()
    task = (
        db.query(ScannerTask)
        .filter(
            ScannerTask.task_uuid == uid,
            ScannerTask.status == "pending",
        )
        .with_for_update()
        .first()
    )
    if not task:
        # 可能已被别的 scanner 认领，或不存在
        return {
            "code": 200,
            "msg": "already_claimed_or_not_found",
            "data": {"claimed": False, "task_uuid": task_uuid},
        }
    # 路由二次校验（防止先查后改期间被改）
    if task.target_scanner_id and task.target_scanner_id != scanner.scanner_id:
        return {
            "code": 200,
            "msg": "pinned_to_other_scanner",
            "data": {"claimed": False, "task_uuid": task_uuid},
        }
    task.status = "running"
    task.scanner_id = scanner.scanner_id
    task.claimed_at = now
    task.started_at = now
    db.commit()
    logger.info(
        "scanner %s 认领 task %s (mode=%s)",
        scanner.scanner_id, task.task_uuid, task.mode,
    )
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "claimed": True,
            "task_uuid": str(task.task_uuid),
            "nmap_args": task.nmap_args,
            "target_summary": task.target_summary,
            "scanner_id": scanner.scanner_id,
        },
    }


# ============================================================================
# PATCH /tasks/{uuid}/report  回写结果
# ============================================================================
@router.patch("/tasks/{task_uuid}/report")
async def report_status(
    task_uuid: str,
    body: dict = Body(...),
    scanner: ScannerAgent = Depends(require_scanner_api_key),
    db: Session = Depends(get_db),
):
    """扫描器回写结果（success / failed + counts）。

    body:
      {
        "status": "success" | "failed" | "cancelled",
        "items_scanned": 37,
        "items_created": 35,
        "items_updated": 2,
        "items_failed": 0,
        "error_message": null,
        "duration_ms": 2340
      }
    """
    uid = _parse_uuid(task_uuid, "task_uuid")
    task = (
        db.query(ScannerTask)
        .filter(ScannerTask.task_uuid == uid, ScannerTask.scanner_id == scanner.scanner_id)
        .first()
    )
    if not task:
        raise HTTPException(
            status_code=404,
            detail="task not found or not claimed by this scanner",
        )

    new_status = body.get("status", "success")
    if new_status not in ("success", "failed", "cancelled"):
        raise HTTPException(status_code=400, detail=f"invalid status: {new_status}")
    task.status = new_status
    task.finished_at = _utcnow()
    if task.started_at:
        task.duration_ms = int((task.finished_at - task.started_at).total_seconds() * 1000)
    for field in ("items_scanned", "items_created", "items_updated", "items_failed"):
        if body.get(field) is not None:
            setattr(task, field, int(body[field]))
    if body.get("error_message"):
        task.error_message = str(body["error_message"])[:1000]
    db.commit()
    logger.info(
        "scanner %s 回报 task %s status=%s items=%d/%d/%d/%d",
        scanner.scanner_id, task.task_uuid, new_status,
        task.items_scanned, task.items_created, task.items_updated, task.items_failed,
    )
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "task_uuid": str(task.task_uuid),
            "status": task.status,
            "finished_at": task.finished_at.isoformat() if task.finished_at else None,
        },
    }