"""OH-UI.4 完整度评分卡 API。

端点：
  GET /api/v1/assets/{asset_id}/completeness

输入：asset_id
输出：
{
  "asset_id": "uuid",
  "overall_score": 75,            # 0-100 综合完整度分
  "state": "valid",                # valid / insufficient_data / error
  "ahs_score": 78,                 # 0-100 AHS（健康分）
  "profile_confidence": 0.85,      # [0,1] 置信度
  "dimensions": {
    "identity": {"covered": true, "evidence_count": 2, "confidence": 0.9},
    "ownership": {"covered": true, ...},
    ...
  },
  "coverage": {
    "total": 8,
    "covered": 6,
    "missing": 2,
    "ratio": 0.75
  },
  "evidence_summary": {
    "total_evidence": 12,
    "sources": ["soc_assets", ...],
    "avg_confidence": 0.85,
    "timespan_hours": 168.0
  },
  "computed_at": "2026-10-03T..."
}

权限：viewer+（只读）
性能：单 asset_id 同步 5s 内返回（OH-2.1 builder 是同步 + 8 loader）
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.asset import Asset
from app.models.user import User
from app.services.asset_profile import (
    build_profile,
    build_profile_dict,
    compute_ahs,
    apply_ahs_to_profile,
    build_evidence_chain,
    CoverageInfo,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["资产完整度"])


# ---------------------------------------------------------------------------
# 端点
# ---------------------------------------------------------------------------


@router.get("/{asset_id}/completeness")
async def get_asset_completeness(
    asset_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取资产完整度评分卡（OH-UI.4）。

    一次性返回八维覆盖 + AHS 健康分 + 证据链摘要。
    前端「完整度评分卡」组件直接消费。
    """
    # 1. 解析资产
    try:
        aid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid asset_id")

    asset = db.query(Asset).filter(Asset.id == aid).first()
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")

    # 2. 同步构建画像（OH-2.1 builder）
    try:
        profile = build_profile(db, asset)
    except Exception as e:
        logger.exception(f"[completeness] build_profile failed for {asset_id}: {e}")
        return {
            "asset_id": asset_id,
            "overall_score": 0,
            "state": "error",
            "error": str(e),
            "computed_at": datetime.now(timezone.utc).isoformat(),
        }

    # 3. 计算 AHS（OH-2.2）
    try:
        ahs_result = compute_ahs(profile)
        profile = apply_ahs_to_profile(profile, ahs_result)
    except Exception as e:
        logger.exception(f"[completeness] compute_ahs failed for {asset_id}: {e}")
        ahs_result = None

    # 4. 生成证据链（OH-2.4）
    try:
        chain = build_evidence_chain(profile)
    except Exception as e:
        logger.exception(f"[completeness] build_evidence_chain failed for {asset_id}: {e}")
        chain = None

    # 5. 组装响应
    return _assemble_response(profile, ahs_result, chain)


# ---------------------------------------------------------------------------
# 组装函数（独立可测）
# ---------------------------------------------------------------------------


def _assemble_response(profile, ahs_result, chain) -> dict:
    """组装完整度评分卡响应。"""
    # 八维明细（per dimension）
    dimensions = {}
    dim_mapping = [
        ("identity", profile.identity),
        ("ownership", profile.ownership),
        ("technology", profile.technology),
        ("exposure", profile.exposure),
        ("vulnerability", profile.vulnerability),
        ("threat", profile.threat),
        ("compliance", profile.compliance),
        ("behavior", profile.behavior),
    ]
    for name, dim in dim_mapping:
        evs = dim.evidence
        if evs:
            avg_conf = sum(e.confidence for e in evs) / len(evs)
            dimensions[name] = {
                "covered": True,
                "evidence_count": len(evs),
                "confidence": round(avg_conf, 4),
            }
        else:
            dimensions[name] = {
                "covered": False,
                "evidence_count": 0,
                "confidence": 0.0,
            }

    # 覆盖率
    total = len(dim_mapping)
    covered = sum(1 for d in dimensions.values() if d["covered"])
    coverage_ratio = round(covered / total, 4) if total else 0.0

    # profile_confidence（profile 自带 computed field）
    profile_confidence = getattr(profile, "profile_confidence", 0.0)

    # AHS
    ahs_score = profile.ahs_score
    ahs_state = ahs_result.state if ahs_result else "ahs_not_computed"

    # overall_score 综合 = coverage_ratio × 100（保留精确度）
    overall_score = round(coverage_ratio * 100, 0)

    # state 判定
    # 使用 AHS 的 state（业务语义上是「画像是否足以计算 AHS」）而不是简单按 covered 计数
    # 原因：AHS 的 insufficient_data 状态本身就是「覆盖维 < 3」，与我们要表达的语义一致
    if ahs_state == "insufficient_data" or covered < 3:
        state = "insufficient_data"
    elif covered == total:
        state = "valid"
    else:
        state = "partial"

    # evidence summary
    evidence_summary = {
        "total_evidence": chain.summary.total_evidence if chain else 0,
        "sources": chain.summary.sources if chain else [],
        "dimensions": chain.summary.dimensions if chain else [],
        "avg_confidence": chain.summary.avg_confidence if chain else 0.0,
        "timespan_hours": chain.summary.timespan_hours if chain else None,
    }

    return {
        "asset_id": profile.asset_id,
        "overall_score": int(overall_score),
        "state": state,
        "ahs_score": ahs_score,
        "ahs_state": ahs_state,
        "profile_confidence": round(profile_confidence, 4),
        "dimensions": dimensions,
        "coverage": {
            "total": total,
            "covered": covered,
            "missing": total - covered,
            "ratio": coverage_ratio,
        },
        "evidence_summary": evidence_summary,
        # OH-UI.5+ 透传证据链时间线（之前仅生成未暴霁前端）。
        # 每条含 evidence_id / dimension / source / observed_at / confidence / reference / note。
        # 默认已 dedup_by_source=True，每 ORM 表最新一条；总 size 约 100B × N entries。
        # 单资产 < 10 KB，批量端点 ≤ 50 个总 < 50 KB，不影响列表性能。
        "evidence_timeline": [e.to_dict() for e in chain.timeline] if chain else [],
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# 批量端点（OH-UI.4 多资产列表卡）
# ---------------------------------------------------------------------------


@router.get("/completeness/batch")
async def get_completeness_batch(
    asset_ids: Optional[str] = Query(
        None,
        description="逗号分隔 asset_id 列表（最多 50 个）；空则返回前 20 个资产",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量获取资产完整度评分卡（资产列表页用）。

    限制：最多 50 个 asset（防止慢查询）。
    """
    # 1. 解析 asset_ids
    ids: list[str] = []
    if asset_ids:
        ids = [s.strip() for s in asset_ids.split(",") if s.strip()]
        if len(ids) > 50:
            raise HTTPException(status_code=400, detail="too many asset_ids (max 50)")
    else:
        # 默认取前 20 个
        rows = db.query(Asset).limit(20).all()
        ids = [str(r.id) for r in rows]

    # 2. 逐个调用
    results = []
    for aid_str in ids:
        try:
            aid = uuid.UUID(aid_str)
        except ValueError:
            results.append({"asset_id": aid_str, "state": "error", "error": "invalid uuid"})
            continue
        asset = db.query(Asset).filter(Asset.id == aid).first()
        if asset is None:
            results.append({"asset_id": aid_str, "state": "error", "error": "asset not found"})
            continue
        try:
            profile = build_profile(db, asset)
            ahs = compute_ahs(profile)
            profile = apply_ahs_to_profile(profile, ahs)
            chain = build_evidence_chain(profile)
            results.append(_assemble_response(profile, ahs, chain))
        except Exception as e:
            logger.warning(f"[completeness/batch] {aid_str} failed: {e}")
            results.append({
                "asset_id": aid_str,
                "state": "error",
                "error": str(e),
            })

    return {"items": results, "total": len(results)}