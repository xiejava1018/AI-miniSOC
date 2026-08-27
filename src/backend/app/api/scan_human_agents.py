"""
扫描器管理端点（人类，admin，P3/F-S3 控制面）

设计依据：docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md §6.4.1

端点（admin 才能注册/注销，viewer+ 列表）：
  - GET   /scan/agents          扫描器列表（含状态/心跳/能力）
  - POST  /scan/agents          注册扫描器（生成 scanner_id + API Key）
  - PATCH /scan/agents/{id}     启用/禁用/编辑能力/子网
  - DELETE /scan/agents/{id}    注销（软删，禁派发）
"""

from __future__ import annotations

import logging
import secrets
import uuid as uuidlib
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.permissions import require_role, require_admin
from app.models.scanner_models import ScannerAgent
from app.models.user import User

logger = logging.getLogger(__name__)
router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ============================================================================
# GET /scan/agents
# ============================================================================
@router.get("/agents")
async def list_agents(
    enabled: Optional[bool] = Query(None),
    status: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(ScannerAgent)
    if enabled is not None:
        q = q.filter(ScannerAgent.enabled == enabled)
    if status:
        q = q.filter(ScannerAgent.status == status)
    items = q.order_by(ScannerAgent.created_at.desc()).all()
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "items": [
                {
                    "scanner_id": a.scanner_id,
                    "name": a.name,
                    "ip": a.ip,
                    "capabilities": a.capabilities,
                    "reachable_subnets": a.reachable_subnets,
                    "status": a.status,
                    "version": a.version,
                    "running_tasks": a.running_tasks,
                    "last_heartbeat": a.last_heartbeat.isoformat() if a.last_heartbeat else None,
                    "enabled": a.enabled,
                    "created_by": a.created_by,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                } for a in items
            ],
        },
    }


# ============================================================================
# POST /scan/agents  注册
# ============================================================================
@router.post("/agents")
async def register_agent(
    body: dict = Body(...),
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """注册扫描器（admin only）。返回 scanner_id + 明文 API Key（仅此一次）。"""
    import hashlib

    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name 不能为空")
    # P4-G: 默认全能力（公网暴露面 + 内网发现 + 端口扫描），操作员可显式取消勾选
    ALLOWED_CAPS = {"public", "internal", "ports"}
    raw_caps = body.get("capabilities")
    if raw_caps is None:
        capabilities = ["public", "internal", "ports"]
    else:
        if not isinstance(raw_caps, list):
            raise HTTPException(status_code=422, detail="capabilities 必须是数组")
        invalid = [c for c in raw_caps if c not in ALLOWED_CAPS]
        if invalid:
            raise HTTPException(
                status_code=422,
                detail=f"capabilities 含非法值 {invalid}，允许: {sorted(ALLOWED_CAPS)}"
            )
        if not raw_caps:
            raise HTTPException(status_code=422, detail="capabilities 不能为空（至少一项）")
        capabilities = raw_caps
    reachable_subnets = body.get("reachable_subnets") or []

    api_key = "sk-scan-" + secrets.token_urlsafe(24)
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    agent = ScannerAgent(
        scanner_id=str(uuidlib.uuid4()),
        name=name,
        ip=body.get("ip"),
        capabilities=capabilities,
        reachable_subnets=reachable_subnets,
        status="unknown",
        api_key_hash=api_key_hash,
        enabled=True,
        created_by=current_user.username,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    logger.info("admin %s 注册扫描器 %s (%s)", current_user.username, name, agent.scanner_id)
    return {
        "code": 200,
        "msg": "success",
        "data": {
            "scanner_id": agent.scanner_id,
            "name": agent.name,
            "api_key": api_key,                      # 仅此次返回
            "api_key_hash_prefix": api_key_hash[:12],
            "capabilities": agent.capabilities,
            "reachable_subnets": agent.reachable_subnets,
            "created_at": agent.created_at.isoformat(),
        },
    }


# ============================================================================
# PATCH /scan/agents/{id}
# ============================================================================
@router.patch("/agents/{scanner_id}")
async def update_agent(
    scanner_id: str,
    body: dict = Body(default_factory=dict),
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    a = db.query(ScannerAgent).filter(ScannerAgent.scanner_id == scanner_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="scanner not found")
    if "name" in body:
        a.name = body["name"]
    if "ip" in body:
        a.ip = body["ip"]
    if "capabilities" in body:
        a.capabilities = body["capabilities"]
    if "reachable_subnets" in body:
        a.reachable_subnets = body["reachable_subnets"]
    if "enabled" in body:
        a.enabled = bool(body["enabled"])
    db.commit()
    return {
        "code": 200,
        "msg": "success",
        "data": {"scanner_id": a.scanner_id, "enabled": a.enabled, "name": a.name},
    }


# ============================================================================
# DELETE /scan/agents/{id}  硬删（admin only）
# ============================================================================
@router.delete("/agents/{scanner_id}")
async def delete_agent(
    scanner_id: str,
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """删除扫描器记录。

    安全门（P4-F）：
      - 拒绝删除 status=online 的 scanner（防误删在线机器 → 任务丢失）
      - 拒绝删除有 pending/running 任务的 scanner（需先取消任务）
      - 物理删除行（不再软删；历史审计由 audit_log 表承担）
      - 落审计日志：action=delete, resource_type=scanner_agent
    """
    from app.services.audit_log_service import AuditLogService
    from app.models.scanner_models import ScannerTask

    a = db.query(ScannerAgent).filter(ScannerAgent.scanner_id == scanner_id).first()
    if not a:
        raise HTTPException(status_code=404, detail=f"scanner {scanner_id} 不存在")

    # 安全门 1: 在线拒绝
    if a.status == "online":
        raise HTTPException(
            status_code=409,
            detail=f"scanner {a.name} 状态为 online，拒绝删除（请先停止该 scanner 进程，"
                   f"约 90s 后状态自动转 offline 后再删）"
        )

    # 安全门 2: 有未完成任务拒绝
    active_tasks = db.query(ScannerTask).filter(
        ScannerTask.target_scanner_id == scanner_id,
        ScannerTask.status.in_(["pending", "running"])
    ).count()
    if active_tasks > 0:
        raise HTTPException(
            status_code=409,
            detail=f"scanner 有 {active_tasks} 个 pending/running 任务，请先取消任务再删除"
        )

    # 清理已结束的关联任务记录（target_scanner_id 留作审计，不强 FK 约束所以不用清）
    # soc_scanner_tasks.target_scanner_id 是 String，无 FK，可保留历史关联

    # 审计日志（删前快照关键字段）
    # AuditLogService.create_audit_log 签名：(self, user_id, username, action, ...)
    # resource_id 是 int，不能直接放 UUID，所以把 scanner 信息放 description + resource_name
    AuditLogService(db).create_audit_log(
        user_id=current_user.id,
        username=current_user.username,
        action="delete",
        resource_type="scanner_agent",
        resource_name=a.name,
        new_values={
            "scanner_id": scanner_id,
            "ip": a.ip,
            "capabilities": a.capabilities,
            "status_before_delete": a.status,
        },
    )

    # 物理删除
    name = a.name
    db.delete(a)
    db.commit()

    logger.info("scanner %s (%s) deleted by %s", scanner_id, name, current_user.username)
    return {
        "code": 200,
        "msg": "success",
        "data": {"scanner_id": scanner_id, "deleted": True, "name": name},
    }