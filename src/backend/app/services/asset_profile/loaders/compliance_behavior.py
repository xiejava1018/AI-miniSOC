"""OH-2.1 T5 — ⑦ 合规维 + ⑧ 行为维 loader。

数据来源：
- 合规：``soc_assets`` (data_classification) + ``soc_compliance_findings`` (latest by asset)
- 行为：``soc_behavior_profiles``（最近 profile_date 一行）
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Asset, ComplianceFinding, BehaviorProfile
from app.services.asset_profile._main import AssetCompliance, AssetBehavior
from app.services.asset_profile._helpers import orm_evidence, safe_load


@safe_load(default=AssetCompliance())
def load_compliance(db: Session, asset: Asset) -> AssetCompliance:
    """⑦ 合规维：从 Asset + ComplianceFinding 聚合三态 + 最新 run 时间。

    注：ComplianceFinding 的时间字段是 ``created_at``（无 checked_at 字段）。
    锚点策略：取 asset 相关的 created_at 最大值作为 run 时间。
    """
    # 取 asset 相关的 created_at 最大值作为锚点
    latest_checked = db.scalar(
        select(func.max(ComplianceFinding.created_at))
        .where(ComplianceFinding.asset_id == asset.id)
    )

    where_clauses = [ComplianceFinding.asset_id == asset.id]
    if latest_checked is not None:
        # 仅取距最新 ≤1 天的 finding 视为同轮（避免跨 run 聚合）
        cutoff = latest_checked - timedelta(days=1)
        where_clauses.append(ComplianceFinding.created_at >= cutoff)

    rows = db.execute(
        select(ComplianceFinding.status, func.count(ComplianceFinding.id))
        .where(*where_clauses)
        .group_by(ComplianceFinding.status)
    ).all()
    counts = {r.status: r[1] for r in rows}

    evidence = [orm_evidence(db, asset, source="soc_compliance_findings")]

    # === S4 Phase 0 等保定级接入（OH-2.7）：资产等级 + 所属系统定级状态 ===
    # 系统定级状态取「最落后」（unrated < suggested < confirmed）——
    # 稽核视角下只要有未定级系统就暴露。
    from app.models.business_system import AssetBusiness, BusinessSystem
    _RANK = {"unrated": 0, "suggested": 1, "confirmed": 2}
    sys_rows = db.execute(
        select(BusinessSystem.rating_status)
        .join(AssetBusiness, AssetBusiness.system_id == BusinessSystem.id)
        .where(AssetBusiness.asset_id == asset.id)
    ).all()
    rated_system_count = len(sys_rows)
    system_rating_status = None
    if sys_rows:
        statuses = [r[0] or "unrated" for r in sys_rows]
        system_rating_status = min(statuses, key=lambda s: _RANK.get(s, 0))
        evidence.append(orm_evidence(db, asset, source="soc_business_systems"))

    return AssetCompliance(
        data_classification=asset.data_classification,
        compliance_pass_count=counts.get("pass", 0),
        compliance_fail_count=counts.get("fail", 0),
        compliance_unknown_count=counts.get("unknown", 0),
        last_compliance_run_at=latest_checked,
        ruleset_version=None,  # ComplianceFinding 无该字段
        protection_level=asset.protection_level,
        protection_level_source=asset.protection_level_source,
        system_rating_status=system_rating_status,
        rated_system_count=rated_system_count,
        evidence=evidence,
    )


@safe_load(default=AssetBehavior())
def load_behavior(db: Session, asset: Asset) -> AssetBehavior:
    """⑧ 行为维：从 BehaviorProfile 取最近 profile_date 一行。"""
    row = db.scalar(
        select(BehaviorProfile)
        .where(BehaviorProfile.asset_id == asset.id)
        .order_by(BehaviorProfile.profile_date.desc())
        .limit(1)
    )

    if row is None:
        return AssetBehavior(
            evidence=[orm_evidence(db, asset, source="soc_behavior_profiles")],
        )

    # tags 是 [{"name": ...}, ...] 格式，提取 name 列表
    tag_names: list[str] = []
    if row.tags and isinstance(row.tags, list):
        for t in row.tags:
            if isinstance(t, dict) and "name" in t:
                tag_names.append(t["name"])

    top_domain_count = len(row.top_domains) if row.top_domains else 0

    evidence = [orm_evidence(db, asset, source="soc_behavior_profiles")]

    # OH-2.8：UEBA 异常评分（纯函数，无额外查询）
    from app.services.identity_ueba import score_behavior_anomaly
    ueba = score_behavior_anomaly(row, asset_type=asset.asset_type)

    return AssetBehavior(
        profile_date=str(row.profile_date) if row.profile_date else None,
        traffic_type=row.traffic_type,
        status=row.status,
        total_visits=row.total or 0,
        top_domain_count=top_domain_count,
        tags=tag_names,
        layer_visit=row.layer_visit or {},
        anomaly_score=ueba.get("anomaly_score"),
        anomaly_signals=ueba.get("signals") or [],
        evidence=evidence,
    )