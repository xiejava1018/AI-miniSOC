"""考核资产真实化稽核（OH-4.3 · S3）

S3 目标：**人为构造项归零**——考核清单里的每一项都必须能回溯到真实
资产/系统实体，不允许「手工维护一份考核资产列表」与系统脱节。

本模块提供两层能力：

1. ``scope_audit(db)``：考核范围真实性稽核
   - 应在范围：有确认等保等级、或属于已确认系统的真实资产
   - 覆盖缺口：已确认系统的成员资产中等级 ``inherited`` 传播未到位的
     （理论上传播引擎已覆盖，此项暴露传播漏跑/被绕过）
   - 脱锚资产：有 ``criticality``/考核标记但不属任何系统、也无 manual
     定级依据 → 无法回溯考核口径

2. ``audit_findings(db, system_id)``：从 **ComplianceFinding 真实稽核
   结果**聚合系统考核清单（pass/fail/unknown 按规则），并对
   范围内资产无任何 finding 的给出 ``no_evidence`` 标记——
   **不伪造 23 项逐项判定**（23 项口径定义属业务侧，见主方案 §12）。

红线：本模块纯只读；考核工单的创建走 remediation_workflow，
不在此自动批量生成（验收口径「工单自动生成」指清单→工单通路已在
S10 具备，批量生成是管理动作，避免无审阅洪水派单）。
"""
from __future__ import annotations

import logging
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.business_system import AssetBusiness, BusinessSystem
from app.models.compliance import ComplianceFinding

logger = logging.getLogger(__name__)

# 最近稽核窗口（天）：超过此窗口无 finding 视为「无当期证据」
RECENT_WINDOW_DAYS = 7


def scope_audit(db: Session) -> Dict[str, Any]:
    """考核范围真实性稽核总览。"""
    # 应在范围的真实资产：manual 定级 或 属于已确认/建议定级的系统
    in_scope = _in_scope_asset_ids(db)
    all_assets = db.query(Asset).all()
    all_ids = {a.id for a in all_assets}

    # 脱锚资产：有资产记录但 (无系统 且 等级非 manual 裁定依据)
    # 注：Asset.protection_level 非空默认 level_2/manual——
    # source=manual 即表示有人工定级依据，不属脱锚。
    member_ids = set(
        db.execute(select(AssetBusiness.asset_id).distinct()).scalars()
    )
    unanchored = [
        _asset_brief(a)
        for a in all_assets
        if a.id not in member_ids and (a.protection_level_source or "") == "inherited"
    ]

    # 覆盖缺口：已确认系统的成员里，等级未继承到位的
    gaps = _propagation_gaps(db)

    # 当期稽核证据覆盖（范围内资产最近窗口有无 finding）
    recent_cutoff = datetime.utcnow() - timedelta(days=RECENT_WINDOW_DAYS)
    evidenced = set(
        db.execute(
            select(ComplianceFinding.asset_id)
            .where(ComplianceFinding.created_at >= recent_cutoff)
            .distinct()
        ).scalars()
    )
    in_scope_no_evidence = [
        _asset_brief(a)
        for a in all_assets
        if a.id in in_scope and a.id not in evidenced
    ]

    return {
        "total_assets": len(all_assets),
        "in_scope_count": len(in_scope),
        "unanchored": unanchored,
        "propagation_gaps": gaps,
        "in_scope_no_evidence": in_scope_no_evidence,
        "finding_count": len(unanchored) + len(gaps) + len(in_scope_no_evidence),
        "recent_window_days": RECENT_WINDOW_DAYS,
        "red_line": "考核项必须回溯真实实体；不伪造判定、不自动批量派单",
    }


def system_findings(db: Session, system_id: Any) -> Dict[str, Any]:
    """系统考核清单：从真实 ComplianceFinding 聚合（近窗口）。"""
    b = db.get(BusinessSystem, system_id)
    if b is None:
        raise LookupError("业务系统不存在")

    members = (
        db.query(Asset)
        .join(AssetBusiness, AssetBusiness.asset_id == Asset.id)
        .filter(AssetBusiness.system_id == b.id)
        .all()
    )
    member_ids = [a.id for a in members]

    # 取最近一轮：成员相关 finding 的 created_at 最大值，回取同轮（±1 天）
    latest = db.scalar(
        select(func.max(ComplianceFinding.created_at)).where(
            ComplianceFinding.asset_id.in_(member_ids)
        )
    ) if member_ids else None

    rows: List[ComplianceFinding] = []
    if latest is not None:
        cutoff = latest - timedelta(days=1)
        rows = list(db.execute(
            select(ComplianceFinding)
            .where(
                ComplianceFinding.asset_id.in_(member_ids),
                ComplianceFinding.created_at >= cutoff,
            )
            .order_by(ComplianceFinding.rule_id)
        ).scalars())

    by_rule: Dict[str, Dict[str, Any]] = {}
    for f in rows:
        r = by_rule.setdefault(f.rule_id, {
            "rule_id": f.rule_id,
            "rule_title": f.rule_title,
            "pass": 0, "fail": 0, "unknown": 0,
        })
        r[f.status] = r.get(f.status, 0) + 1

    evidenced_ids = {f.asset_id for f in rows}
    no_evidence = [
        _asset_brief(a) for a in members if a.id not in evidenced_ids
    ]

    status_totals = Counter(f.status for f in rows)
    judged = status_totals["pass"] + status_totals["fail"]
    compliance_rate = (
        round(status_totals["pass"] * 100.0 / judged, 1) if judged else None
    )

    return {
        "system": {"id": str(b.id), "code": b.code, "name": b.name,
                   "rating_status": b.rating_status or "unrated"},
        "member_count": len(members),
        "latest_run_at": latest.isoformat() if latest else None,
        "by_rule": sorted(by_rule.values(), key=lambda x: x["rule_id"]),
        "status_totals": dict(status_totals),
        "compliance_rate": compliance_rate,
        "no_evidence_assets": no_evidence,
        "note": "清单由真实稽核结果聚合；23 项口径以业务侧定义为准",
    }


# ---------------- internals ----------------

def _in_scope_asset_ids(db: Session) -> set:
    """有确认定级（系统 confirmed/suggested 成员）或 manual 定级依据。"""
    rows = db.execute(
        select(AssetBusiness.asset_id)
        .join(BusinessSystem, BusinessSystem.id == AssetBusiness.system_id)
        .where(BusinessSystem.rating_status.in_(["confirmed", "suggested"]))
        .distinct()
    ).scalars()
    ids = set(rows)
    for a in db.query(Asset).all():
        if (a.protection_level_source or "manual") == "manual":
            ids.add(a.id)
    return ids


def _propagation_gaps(db: Session) -> List[Dict[str, Any]]:
    """已确认系统成员中等级低于系统等级的资产（传播漏跑）。"""
    from app.services.protection_level_propagation import PL_RANK

    out: List[Dict[str, Any]] = []
    confirmed = db.query(BusinessSystem).filter(
        BusinessSystem.rating_status == "confirmed"
    ).all()
    for b in confirmed:
        target = PL_RANK.get(b.protection_level or "", -1)
        if target < 0:
            continue
        members = (
            db.query(Asset)
            .join(AssetBusiness, AssetBusiness.asset_id == Asset.id)
            .filter(AssetBusiness.system_id == b.id)
            .all()
        )
        for a in members:
            if PL_RANK.get(a.protection_level or "", -1) < target:
                out.append({
                    **_asset_brief(a),
                    "system": b.name,
                    "expected": b.protection_level,
                    "actual": a.protection_level,
                })
    return out


def _asset_brief(a: Asset) -> Dict[str, Any]:
    return {
        "asset_id": str(a.id),
        "name": a.name,
        "asset_ip": a.asset_ip,
        "protection_level": a.protection_level,
        "protection_level_source": a.protection_level_source,
    }
