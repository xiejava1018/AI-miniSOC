"""
合规基线 API（PRD F3.3）

端点分层对应双层架构：
- 判定层（无 LLM）：run-check / latest / findings / rules / assets/{id}
- 解读层（LLM）  ：interpret（仅对 fail 生成整改建议）

路由注册顺序注意：本文件全部路径为 /assets/compliance/**（静态两段），
必须在 assets.router 之前注册，否则被 /assets/{asset_id} 抢匹配。
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.permissions import require_button_permission
from app.models import Asset, ComplianceRun
from app.models.user import User
from app.services.compliance import ComplianceService, load_ruleset
from app.services.compliance_ai import ComplianceAIService

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_uuid(value: str, label: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise HTTPException(status_code=400, detail=f"{label} 格式不正确")


def _run_out(run: ComplianceRun) -> dict:
    return {
        "id": str(run.id),
        "ruleset_version": run.ruleset_version,
        "ruleset_name": run.ruleset_name,
        "rules_total": run.rules_total,
        "assets_total": run.assets_total,
        "assets_in_scope": run.assets_in_scope,
        "pass_count": run.pass_count,
        "fail_count": run.fail_count,
        "unknown_count": run.unknown_count,
        "compliance_rate": run.compliance_rate,
        "coverage_rate": run.coverage_rate,
        "stats": run.stats or {},
        "triggered_by": run.triggered_by,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


def _finding_out(f) -> dict:
    return {
        "id": str(f.id),
        "asset_id": str(f.asset_id),
        "rule_id": f.rule_id,
        "rule_version": f.rule_version,
        "rule_title": f.rule_title,
        "category": f.category,
        "severity": f.severity,
        "status": f.status,
        "reason": f.reason,
        "evidence": f.evidence or {},
        "ai_remediation": f.ai_remediation,
        "ai_model": f.ai_model,
        "ai_prompt_version": f.ai_prompt_version,
        "ai_generated_at": f.ai_generated_at.isoformat() if f.ai_generated_at else None,
    }


# ---------------------------------------------------------------------------
# 规则库（审计可见：规则原文即判定依据）
# ---------------------------------------------------------------------------

@router.get("/compliance/rules", summary="合规规则库（含版本，审计对照用）")
async def get_rules(current_user: User = Depends(get_current_user)):
    rs = load_ruleset()
    return {
        "ruleset_version": rs.get("ruleset_version"),
        "ruleset_name": rs.get("ruleset_name"),
        "updated_at": rs.get("updated_at"),
        "notes": rs.get("notes") or {},
        "rules": rs.get("rules") or [],
        # 非空即意味着巡检覆盖不完整，必须让使用者看到
        "invalid_rules": rs.get("invalid_rules") or [],
    }


# ---------------------------------------------------------------------------
# 判定层（确定性，无 LLM）
# ---------------------------------------------------------------------------

@router.post("/compliance/run-check", summary="执行合规巡检（规则判定，不调 AI）")
async def run_check(
    db: Session = Depends(get_db),
    # X1 权限矩阵：巡检属于运维写操作，viewer/auditor 不可触发
    current_user: User = Depends(require_button_permission("compliance", "check")),
):
    run = ComplianceService(db).run_check(triggered_by=current_user.username)
    return {"message": "巡检完成", "run": _run_out(run)}


@router.get("/compliance/latest", summary="最近一次巡检结果")
async def latest(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = ComplianceService(db).latest_run()
    if not run:
        return {"run": None, "message": "尚无巡检记录，请先执行巡检"}
    return {"run": _run_out(run)}


@router.get("/compliance/findings", summary="问题项列表（fail / unknown）")
async def list_findings(
    run_id: Optional[str] = Query(None, description="默认取最近一次巡检"),
    status: Optional[str] = Query(None, pattern="^(fail|unknown)$"),
    severity: Optional[str] = Query(None, pattern="^(critical|high|medium|low)$"),
    rule_id: Optional[str] = Query(None, max_length=32),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = ComplianceService(db)
    if run_id:
        rid = _parse_uuid(run_id, "run_id")
    else:
        run = svc.latest_run()
        if not run:
            return {"total": 0, "page": page, "page_size": page_size, "records": []}
        rid = run.id

    data = svc.findings(rid, status=status, severity=severity, rule_id=rule_id,
                        page=page, page_size=page_size)

    # 补资产名/IP，避免前端 N+1
    records = [_finding_out(f) for f in data["records"]]
    asset_ids = {f["asset_id"] for f in records}
    if asset_ids:
        rows = db.query(Asset.id, Asset.name, Asset.asset_ip).filter(
            Asset.id.in_([uuid.UUID(a) for a in asset_ids])).all()
        amap = {str(r[0]): {"asset_name": r[1], "asset_ip": r[2]} for r in rows}
        for f in records:
            f.update(amap.get(f["asset_id"], {"asset_name": None, "asset_ip": None}))

    return {"total": data["total"], "page": data["page"],
            "page_size": data["page_size"], "run_id": str(rid), "records": records}


@router.get("/compliance/assets/{asset_id}", summary="单资产逐规则判定（即时重算）")
async def asset_compliance(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    aid = _parse_uuid(asset_id, "asset_id")
    asset = db.query(Asset).filter(Asset.id == aid).first()
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")
    return ComplianceService(db).evaluate_asset(asset)


# ---------------------------------------------------------------------------
# 解读层（LLM，只读 fail 结果）
# ---------------------------------------------------------------------------

@router.post("/compliance/interpret", summary="AI 生成整改建议（仅 fail 项）")
async def interpret(
    run_id: Optional[str] = Query(None, description="默认取最近一次巡检"),
    limit: int = Query(10, ge=1, le=50, description="单次生成上限（控成本）"),
    force: bool = Query(False, description="是否重新生成已有建议"),
    db: Session = Depends(get_db),
    # X1：AI 解读消耗 token 且产出可操作建议，与巡检同等控制
    current_user: User = Depends(require_button_permission("compliance", "interpret")),
):
    svc = ComplianceService(db)
    if run_id:
        rid = _parse_uuid(run_id, "run_id")
    else:
        run = svc.latest_run()
        if not run:
            raise HTTPException(status_code=400, detail="尚无巡检记录，请先执行巡检")
        rid = run.id
    stats = ComplianceAIService(db).interpret_run(rid, limit=limit, force=force)
    return {"message": "解读完成", "run_id": str(rid), "stats": stats}
