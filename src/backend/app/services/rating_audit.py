"""定级备案稽核（OH-4.12 · S4 Phase 0 辅助定级）

S4 红线（主方案 §0）：系统**只建议不裁决**，本模块是稽核/差距分析，
不做任何定级动作。三类稽核发现：

  1. ``unrated``     未定级且无建议 → 应先跑建议引擎
  2. ``pending``     有建议未人工确认 → 待确认（不催办，仅展示）
  3. ``divergence``  已确认等级低于建议等级 → 差距提示（确认可能偏低，
                     也可能建议偏保守——人工判断，系统不裁决）

一致性公理（本体 A2 弱化版）：业务系统等级应 ≥ 成员资产最高等级
（成员 manual 等级高于系统 → 一致性告警，等保一致性稽核）。

挂载：GET /business-systems/rating-audit + /{id}/rating-gap
（静态路径先于 /{system_id} catch-all，与 coverage-kpi 同款）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.business_system import AssetBusiness, BusinessSystem
from app.services.protection_level_propagation import PL_RANK

logger = logging.getLogger(__name__)

# 稽核发现类型
FINDING_UNRATED = "unrated"
FINDING_PENDING = "pending"
FINDING_DIVERGENCE = "divergence"
FINDING_MEMBER_EXCEEDS = "member_exceeds_system"


def audit(db: Session) -> Dict[str, Any]:
    """S4 定级稽核总览：状态分布 + 逐系统发现列表。"""
    systems = db.query(BusinessSystem).order_by(BusinessSystem.name).all()

    findings: List[Dict[str, Any]] = []
    dist = {"unrated": 0, "suggested": 0, "confirmed": 0}
    for b in systems:
        status = b.rating_status or "unrated"
        dist[status] = dist.get(status, 0) + 1

        if status == "unrated":
            findings.append(_finding(b, FINDING_UNRATED,
                                     "未定级且无建议——先运行建议引擎"))
        elif status == "suggested":
            findings.append(_finding(
                b, FINDING_PENDING,
                f"建议 {b.suggested_protection_level} 待人工确认（PUT protection_level 确认）",
            ))
        elif status == "confirmed" and b.suggested_protection_level:
            s_rank = PL_RANK.get(b.suggested_protection_level, -1)
            c_rank = PL_RANK.get(b.protection_level or "", -1)
            if s_rank > c_rank:
                findings.append(_finding(
                    b, FINDING_DIVERGENCE,
                    f"已确认 {b.protection_level} 低于建议 "
                    f"{b.suggested_protection_level}——请人工复核（系统不裁决）",
                ))

        # 一致性公理：成员 manual 等级 > 系统等级
        exceeds = _members_exceeding(db, b)
        if exceeds:
            findings.append(_finding(
                b, FINDING_MEMBER_EXCEEDS,
                f"{len(exceeds)} 个成员资产等级高于系统等级："
                + "、".join(
                    f"{a['name']}({a['protection_level']})" for a in exceeds[:3]
                ),
                members=exceeds,
            ))

    # 覆盖率（S4 Phase 0 KPI：建议覆盖率 ≥80%）
    total = len(systems)
    with_suggestion = sum(
        1 for b in systems if b.suggested_protection_level
    )
    confirmed = dist["confirmed"]

    return {
        "total_systems": total,
        "distribution": dist,
        "suggestion_coverage": round(with_suggestion * 100.0 / total, 1) if total else 0.0,
        "confirmed_rate": round(confirmed * 100.0 / total, 1) if total else 0.0,
        "findings": findings,
        "finding_count": len(findings),
        "red_line": "系统只建议不裁决；所有等级变更均须人工确认",
    }


def gap_analysis(db: Session, system_id: Any) -> Dict[str, Any]:
    """单系统定级差距分析（当前等级 vs 建议 vs 成员分布）。"""
    b = db.get(BusinessSystem, system_id)
    if b is None:
        raise LookupError("业务系统不存在")

    members = (
        db.query(Asset, AssetBusiness.role)
        .join(AssetBusiness, AssetBusiness.asset_id == Asset.id)
        .filter(AssetBusiness.system_id == b.id)
        .all()
    )
    member_levels = {"inherited": 0, "manual": 0, "none": 0}
    highest_member: Optional[Dict[str, Any]] = None
    highest_rank = -1
    for a, _role in members:
        src = a.protection_level_source or "manual"
        lv = a.protection_level
        if not lv:
            member_levels["none"] += 1
        elif src == "inherited":
            member_levels["inherited"] += 1
        else:
            member_levels["manual"] += 1
        r = PL_RANK.get(lv or "", -1)
        if r > highest_rank:
            highest_rank = r
            highest_member = {"name": a.name, "protection_level": lv}

    suggested = b.suggested_protection_level
    confirmed_level = b.protection_level
    s_rank = PL_RANK.get(suggested or "", -1)
    c_rank = PL_RANK.get(confirmed_level or "", -1)

    gap: Optional[str] = None
    if suggested and confirmed_level:
        if s_rank > c_rank:
            gap = "confirmed_below_suggested"
        elif s_rank < c_rank:
            gap = "confirmed_above_suggested"
        else:
            gap = "aligned"

    return {
        "system": {
            "id": str(b.id), "code": b.code, "name": b.name,
            "rating_status": b.rating_status or "unrated",
            "confirmed_level": confirmed_level,
            "suggested_level": suggested,
            "suggestion_basis": b.suggestion_basis,
            "confirmed_by": b.rating_confirmed_by,
            "confirmed_at": b.rating_confirmed_at.isoformat()
            if b.rating_confirmed_at else None,
        },
        "member_summary": {
            "count": len(members),
            "level_sources": member_levels,
            "highest_member": highest_member,
        },
        "gap": gap,
        "consistency": (
            "member_exceeds_system" if highest_rank > c_rank >= 0 else "ok"
        ),
        "red_line": "差距分析仅供人工复核，系统不自动调整等级",
    }


def _members_exceeding(db: Session, b: BusinessSystem) -> List[Dict[str, Any]]:
    """manual 等级高于系统等级的成员资产。"""
    sys_rank = PL_RANK.get(b.protection_level or "", -1)
    if sys_rank < 0:
        return []
    rows = (
        db.query(Asset)
        .join(AssetBusiness, AssetBusiness.asset_id == Asset.id)
        .filter(AssetBusiness.system_id == b.id)
        .all()
    )
    return [
        {"asset_id": str(a.id), "name": a.name,
         "protection_level": a.protection_level}
        for a in rows
        if PL_RANK.get(a.protection_level or "", -1) > sys_rank
    ]


def _finding(b: BusinessSystem, kind: str, message: str,
             **extra: Any) -> Dict[str, Any]:
    return {
        "system_id": str(b.id),
        "system_name": b.name,
        "rating_status": b.rating_status or "unrated",
        "kind": kind,
        "message": message,
        **extra,
    }
