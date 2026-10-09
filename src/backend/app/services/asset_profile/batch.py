"""OH-2.5 批量画像构建器（性能治本版）。

背景（2026-10-09）：`completeness/aggregate` 原先对每台资产各跑一遍 8 个 loader，
每台 14+ 条独立 SQL；100 资产 = 1400+ 次串行 DB 往返。生产（本机 PG）2~3s 可接受，
但 dev 后端连远端公网 testdb（111.228.57.2，RTT 20-50ms）时总耗时 40-60s，
必然超前端 30s 超时。

本模块把所有查询改为 `asset_id IN (...)` 的 GROUP BY / DISTINCT ON 批量形态：
- 总 SQL 次数与资产数无关（约 12 条）
- 单资产维度组装逻辑与 `loaders/` 逐资产版保持**口径一致**（字段、
  置信度规则、evidence source、"同一轮合规 run ≤1d"窗口全部对齐）
- 单维度批量查询失败只影响该维（与 @safe_load 兜底语义一致），返回空 dict → 空 dataclass

不在本模块做的事：coverage / profile_confidence / AHS / evidence_chain 均为纯函数，
由调用方（api/asset_completeness.py）复用 _main.py / ahs_service / evidence_chain。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Sequence

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.models import (
    Asset,
    AssetBusiness,
    AssetIncident,
    AssetPort,
    BehaviorProfile,
    BusinessSystem,
    ComplianceFinding,
    Incident,
)
from app.models.asset_source import AssetSource
from app.models.identity import IdentityBinding
from app.models.vulnerability import AssetVulnerability as ORMAssetVulnerability, Vulnerability
from app.services.asset_profile._helpers import orm_evidence
from app.services.asset_profile._main import (
    AssetBehavior,
    AssetCompliance,
    AssetExposure,
    AssetIdentity,
    AssetOwnership,
    AssetProfile,
    AssetTechnology,
    AssetThreat,
    AssetVulnerability,
    compute_coverage,
    compute_profile_confidence,
)

logger = logging.getLogger(__name__)


def _sk(x) -> str:
    """dict key 归一化：各表 asset_id 列类型不一（UUID 对象 / str），统一 str。"""
    return str(x)

# 与 loaders/risk_dims.py 一致
_SEVERITY_RANK = {"critical": 4, "high": 3, "medium": 2, "low": 1}
# 与 loaders/compliance_behavior.py 一致
_RATING_RANK = {"unrated": 0, "suggested": 1, "confirmed": 2}


def build_profiles_batch(db: Session, assets: Sequence[Asset]) -> List[AssetProfile]:
    """批量构建多资产八维画像（口径 = builder.build_profile 逐资产版）。

    返回顺序与 assets 一致；单维批量查询失败 → 该维空 dataclass（不抛）。
    """
    if not assets:
        return []
    ids = [a.id for a in assets]

    # 注意：各表 asset_id 列类型不一（如 BehaviorProfile 是 UUID(as_uuid=False) → str，
    # Asset.id 是 UUID 对象）。统一把批量 map 的 key 归一为 str，避免 dict lookup 落空。
    def _skeys(d: Dict) -> Dict:
        return {str(k): v for k, v in d.items()}

    identity_map = _skeys(_load_identity_batch(db, ids))
    ownership_map = _skeys(_load_ownership_batch(db, ids))
    tech_map = _skeys(_load_technology_batch(db, ids))
    exposure_map = _skeys(_load_exposure_batch(db, ids))
    vuln_map = _skeys(_load_vulnerability_batch(db, ids))
    threat_map = _skeys(_load_threat_batch(db, ids))
    compliance_map = _skeys(_load_compliance_batch(db, ids))
    behavior_map = _skeys(_load_behavior_batch(db, ids))

    profiles: List[AssetProfile] = []
    for asset in assets:
        aid = str(asset.id)
        p0 = AssetProfile(
            asset_id=aid,
            identity=identity_map.get(aid, AssetIdentity()),
            ownership=ownership_map.get(aid, AssetOwnership()),
            technology=tech_map.get(aid, AssetTechnology()),
            exposure=exposure_map.get(aid, AssetExposure()),
            vulnerability=vuln_map.get(aid, AssetVulnerability()),
            threat=threat_map.get(aid, AssetThreat()),
            compliance=compliance_map.get(aid, AssetCompliance()),
            behavior=behavior_map.get(aid, AssetBehavior()),
        )
        cov = compute_coverage(p0)
        conf = compute_profile_confidence(
            AssetProfile(
                asset_id=p0.asset_id, identity=p0.identity, ownership=p0.ownership,
                technology=p0.technology, exposure=p0.exposure, vulnerability=p0.vulnerability,
                threat=p0.threat, compliance=p0.compliance, behavior=p0.behavior,
                coverage=cov,
            )
        )
        profiles.append(
            AssetProfile(
                asset_id=p0.asset_id, identity=p0.identity, ownership=p0.ownership,
                technology=p0.technology, exposure=p0.exposure, vulnerability=p0.vulnerability,
                threat=p0.threat, compliance=p0.compliance, behavior=p0.behavior,
                coverage=cov, profile_confidence=conf,
            )
        )
    return profiles


# ---------------------------------------------------------------------------
# 各维批量 loader（返回 {asset_id: dim_dataclass}；缺失 key = 该维空）
# ---------------------------------------------------------------------------


def _load_identity_batch(db: Session, ids) -> Dict:
    try:
        bindings = {
            _sk(r[0]): r[1]
            for r in db.execute(
                select(IdentityBinding.asset_id, func.count(IdentityBinding.id))
                .where(IdentityBinding.asset_id.in_(ids))
                .group_by(IdentityBinding.asset_id)
            ).all()
        }
        sources = {
            _sk(r[0]): r[1]
            for r in db.execute(
                select(AssetSource.asset_id, func.count(AssetSource.id))
                .where(AssetSource.asset_id.in_(ids))
                .group_by(AssetSource.asset_id)
            ).all()
        }
        # 每资产最近一条 binding 的 account（hostname fallback）——DISTINCT ON（PG 专属）
        # 每资产最近一条 binding 的 account（hostname fallback）——row_number 窗口取每资产最新一条
        def _latest_per_asset(stmt):
            sub = stmt.subquery()
            return {_sk(r[0]): r[1] for r in db.execute(select(sub.c.asset_id, sub.c.value).where(sub.c.rn == 1)).all()}

        latest_binding = _latest_per_asset(
            select(
                IdentityBinding.asset_id.label("asset_id"),
                IdentityBinding.account.label("value"),
                func.row_number()
                .over(
                    partition_by=IdentityBinding.asset_id,
                    order_by=IdentityBinding.last_seen.desc(),
                )
                .label("rn"),
            ).where(IdentityBinding.asset_id.in_(ids))
        )
        latest_source = _latest_per_asset(
            select(
                AssetSource.asset_id.label("asset_id"),
                AssetSource.source_id.label("value"),
                func.row_number()
                .over(
                    partition_by=AssetSource.asset_id,
                    order_by=AssetSource.last_seen_at.desc(),
                )
                .label("rn"),
            ).where(AssetSource.asset_id.in_(ids))
        )
    except Exception:
        logger.exception("[batch] identity dim failed")
        return {}

    out: Dict = {}
    for asset in _assets_in(db, ids):
        aid = asset.id
        bindings_count = bindings.get(_sk(aid), 0)
        sources_count = sources.get(_sk(aid), 0)
        total_refs = bindings_count + sources_count
        if total_refs >= 3:
            identity_confidence = 1.0
        elif total_refs >= 1:
            identity_confidence = 0.8
        elif asset.wazuh_agent_id or asset.data_source:
            identity_confidence = 0.5
        else:
            identity_confidence = 0.0
        hostname = asset.name
        if not hostname and bindings_count > 0:
            hostname = latest_binding.get(_sk(aid))
        evidence = [orm_evidence(db, asset, source="soc_assets")]
        if sources_count > 0:
            evidence.append(orm_evidence(db, asset, source="soc_asset_sources"))
        out[_sk(aid)] = AssetIdentity(
            source_id=latest_source.get(_sk(aid)),
            data_source=asset.data_source,
            wazuh_agent_id=asset.wazuh_agent_id,
            mac_address=str(asset.mac_address) if asset.mac_address else None,
            hostname=hostname,
            identity_confidence=identity_confidence,
            identity_bindings_count=bindings_count,
            evidence=evidence,
        )
    return out


def _assets_in(db: Session, ids):
    """按 id 取 ORM 资产。session identity_map 已有这些实例（调用方刚加载），不发 SQL。"""
    return [db.get(Asset, i) for i in ids]


def _load_ownership_batch(db: Session, ids) -> Dict:
    try:
        rows = db.execute(
            select(AssetBusiness.asset_id, BusinessSystem.name, BusinessSystem.code)
            .join(BusinessSystem, AssetBusiness.system_id == BusinessSystem.id)
            .where(AssetBusiness.asset_id.in_(ids))
        ).all()
    except Exception:
        logger.exception("[batch] ownership dim failed")
        return {}
    sys_map: Dict = defaultdict(list)
    for r in rows:
        sys_map[_sk(r.asset_id)].append((r.name, r.code))

    out: Dict = {}
    for asset in _assets_in(db, ids):
        pairs = sys_map.get(_sk(asset.id), [])
        out[_sk(asset.id)] = AssetOwnership(
            owner=asset.owner,
            owner_contact=asset.owner_contact,
            business_unit=asset.business_unit,
            business_impact=asset.business_impact,
            data_sensitivity=asset.data_sensitivity,
            protection_level=asset.protection_level,
            business_systems=[p[0] for p in pairs],
            business_system_codes=[p[1] for p in pairs],
            evidence=[orm_evidence(db, asset, source="soc_assets")],
        )
    return out


def _load_technology_batch(db: Session, ids) -> Dict:
    try:
        rows = db.execute(
            select(AssetPort.asset_id, AssetPort.service, func.count(AssetPort.id))
            .where(AssetPort.asset_id.in_(ids), AssetPort.state == "open")
            .group_by(AssetPort.asset_id, AssetPort.service)
        ).all()
    except Exception:
        logger.exception("[batch] technology dim failed")
        return {}
    svc_map: Dict = defaultdict(dict)  # aid -> {service: count}
    for r in rows:
        svc_map[_sk(r.asset_id)][r.service] = r[2]

    out: Dict = {}
    for asset in _assets_in(db, ids):
        per = svc_map.get(_sk(asset.id), {})
        out[_sk(asset.id)] = AssetTechnology(
            os_name=asset.os_name,
            os_version=asset.os_version,
            hardware_info=asset.hardware_info or {},
            open_ports_count=sum(per.values()),
            services=sorted([s for s in per if s]),
            components=[],  # SBOM 占位（与逐资产版一致）
            evidence=[orm_evidence(db, asset, source="soc_assets")],
        )
    return out


def _load_exposure_batch(db: Session, ids) -> Dict:
    assets = _assets_in(db, ids)
    # 只有 public_ip 非空的资产才查端口（与逐资产版一致）
    pub_ids = [a.id for a in assets if a.public_ip]
    port_map: Dict = defaultdict(list)
    if pub_ids:
        try:
            rows = db.execute(
                select(AssetPort.asset_id, AssetPort.port)
                .where(AssetPort.asset_id.in_(pub_ids), AssetPort.state == "open")
                .order_by(AssetPort.port)
            ).all()
            for r in rows:
                port_map[_sk(r.asset_id)].append(r.port)
        except Exception:
            logger.exception("[batch] exposure dim failed")
            return {}

    out: Dict = {}
    for asset in assets:
        out[_sk(asset.id)] = AssetExposure(
            public_ip=asset.public_ip,
            exposure_level=asset.exposure_level,
            nat_mapped_internal_ips=[],
            exposed_ports=port_map.get(_sk(asset.id), []) if asset.public_ip else [],
            wan_ip=None,
            evidence=[orm_evidence(db, asset, source="soc_assets")],
        )
    return out


def _load_vulnerability_batch(db: Session, ids) -> Dict:
    try:
        rows = db.execute(
            select(
                ORMAssetVulnerability.asset_id,
                Vulnerability.severity,
                func.count(ORMAssetVulnerability.id),
            )
            .join(Vulnerability, ORMAssetVulnerability.vulnerability_id == Vulnerability.id)
            .where(ORMAssetVulnerability.asset_id.in_(ids))
            .group_by(ORMAssetVulnerability.asset_id, Vulnerability.severity)
        ).all()
        unfixed_rows = {
            _sk(r[0]): r[1]
            for r in db.execute(
                select(ORMAssetVulnerability.asset_id, func.count(ORMAssetVulnerability.id))
                .join(Vulnerability, Vulnerability.id == ORMAssetVulnerability.vulnerability_id)
                .where(
                    ORMAssetVulnerability.asset_id.in_(ids),
                    ORMAssetVulnerability.status == "open",
                    Vulnerability.severity.in_(["critical", "high"]),
                )
                .group_by(ORMAssetVulnerability.asset_id)
            ).all()
        }
    except Exception:
        logger.exception("[batch] vulnerability dim failed")
        return {}

    sev_map: Dict = defaultdict(dict)
    for r in rows:
        sev_map[_sk(r.asset_id)][r.severity] = r[2]

    out: Dict = {}
    for asset in _assets_in(db, ids):
        by_sev = sev_map.get(_sk(asset.id), {})
        out[_sk(asset.id)] = AssetVulnerability(
            risk_score=asset.risk_score,
            risk_summary=asset.risk_summary,
            risk_scored_at=asset.risk_scored_at,
            score_breakdown=asset.score_breakdown or {},
            vuln_total=sum(by_sev.values()),
            vuln_by_severity=by_sev,
            unfixed_high_count=unfixed_rows.get(_sk(asset.id), 0),
            evidence=[
                orm_evidence(db, asset, source="soc_assets"),
                orm_evidence(db, asset, source="soc_asset_vulnerabilities"),
            ],
        )
    return out


def _load_threat_batch(db: Session, ids) -> Dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    try:
        # open 告警按 severity 分档
        open_rows = db.execute(
            select(AssetIncident.asset_id, Incident.severity, func.count(Incident.id))
            .join(Incident, AssetIncident.incident_id == Incident.id)
            .where(AssetIncident.asset_id.in_(ids), Incident.status == "open")
            .group_by(AssetIncident.asset_id, Incident.severity)
        ).all()
        # 近 30d 事件数（基于 created_at，与逐资产版一致）
        recent_rows = {
            _sk(r[0]): r[1]
            for r in db.execute(
                select(AssetIncident.asset_id, func.count(Incident.id))
                .join(Incident, AssetIncident.incident_id == Incident.id)
                .where(AssetIncident.asset_id.in_(ids), Incident.created_at >= cutoff)
                .group_by(AssetIncident.asset_id)
            ).all()
        }
    except Exception:
        logger.exception("[batch] threat dim failed")
        return {}

    sev_map: Dict = defaultdict(dict)
    for r in open_rows:
        sev_map[_sk(r.asset_id)][r.severity] = r[2]

    out: Dict = {}
    for asset in _assets_in(db, ids):
        per = sev_map.get(_sk(asset.id), {})
        open_alerts = sum(per.values())
        highest = None
        if per:
            highest = max(per, key=lambda s: _SEVERITY_RANK.get(s, 0))
        out[_sk(asset.id)] = AssetThreat(
            open_alerts=open_alerts,
            highest_alert_level=highest,
            recent_incident_count_30d=recent_rows.get(_sk(asset.id), 0),
            attack_patterns=[],  # OH-4.4 占位（与逐资产版一致）
            evidence=[orm_evidence(db, asset, source="soc_incidents")],
        )
    return out


def _load_compliance_batch(db: Session, ids) -> Dict:
    try:
        # 每资产最新 finding 时间（run 锚点）
        max_rows = {
            _sk(r[0]): r[1]
            for r in db.execute(
                select(ComplianceFinding.asset_id, func.max(ComplianceFinding.created_at))
                .where(ComplianceFinding.asset_id.in_(ids))
                .group_by(ComplianceFinding.asset_id)
            ).all()
        }
        # 同一轮 run（≤1d 窗口）内的三态计数：join 子查询按各资产锚点过滤
        anchor = (
            select(
                ComplianceFinding.asset_id.label("aid"),
                func.max(ComplianceFinding.created_at).label("mx"),
            )
            .where(ComplianceFinding.asset_id.in_(ids))
            .group_by(ComplianceFinding.asset_id)
            .subquery()
        )
        count_rows = db.execute(
            select(ComplianceFinding.asset_id, ComplianceFinding.status, func.count(ComplianceFinding.id))
            .join(anchor, ComplianceFinding.asset_id == anchor.c.aid)
            .where(ComplianceFinding.created_at >= anchor.c.mx - text("interval '1 day'"))
            .group_by(ComplianceFinding.asset_id, ComplianceFinding.status)
        ).all()
        # 业务系统定级状态（每资产全部挂靠系统，取最落后）
        rating_rows = db.execute(
            select(AssetBusiness.asset_id, BusinessSystem.rating_status)
            .join(BusinessSystem, AssetBusiness.system_id == BusinessSystem.id)
            .where(AssetBusiness.asset_id.in_(ids))
        ).all()
    except Exception:
        logger.exception("[batch] compliance dim failed")
        return {}

    status_map: Dict = defaultdict(dict)
    for r in count_rows:
        status_map[_sk(r.asset_id)][r.status] = r[2]
    rating_map: Dict = defaultdict(list)
    for r in rating_rows:
        rating_map[_sk(r.asset_id)].append(r.rating_status)

    out: Dict = {}
    for asset in _assets_in(db, ids):
        counts = status_map.get(_sk(asset.id), {})
        ratings = [s or "unrated" for s in rating_map.get(_sk(asset.id), [])]
        evidence = [orm_evidence(db, asset, source="soc_compliance_findings")]
        system_rating_status = None
        if ratings:
            system_rating_status = min(ratings, key=lambda s: _RATING_RANK.get(s, 0))
            evidence.append(orm_evidence(db, asset, source="soc_business_systems"))
        out[_sk(asset.id)] = AssetCompliance(
            data_classification=asset.data_classification,
            compliance_pass_count=counts.get("pass", 0),
            compliance_fail_count=counts.get("fail", 0),
            compliance_unknown_count=counts.get("unknown", 0),
            last_compliance_run_at=max_rows.get(_sk(asset.id)),
            ruleset_version=None,
            protection_level=asset.protection_level,
            protection_level_source=asset.protection_level_source,
            system_rating_status=system_rating_status,
            rated_system_count=len(ratings),
            evidence=evidence,
        )
    return out


def _load_behavior_batch(db: Session, ids) -> Dict:
    from app.services.identity_ueba import score_behavior_anomaly

    try:
        # 每资产最近 profile_date 一行（row_number 窗口）
        sub = (
            select(
                BehaviorProfile.asset_id.label("asset_id"),
                BehaviorProfile.id.label("row_id"),
                func.row_number()
                .over(
                    partition_by=BehaviorProfile.asset_id,
                    order_by=BehaviorProfile.profile_date.desc(),
                )
                .label("rn"),
            )
            .where(BehaviorProfile.asset_id.in_(ids))
            .subquery()
        )
        rows = db.execute(
            select(BehaviorProfile)
            .join(sub, BehaviorProfile.id == sub.c.row_id)
            .where(sub.c.rn == 1)
        ).scalars().all()
    except Exception:
        logger.exception("[batch] behavior dim failed")
        return {}
    # 列类型 UUID(as_uuid=False) → key 为 str；统一 str 化防类型不匹配
    bp_map = {str(bp.asset_id): bp for bp in rows}

    out: Dict = {}
    for asset in _assets_in(db, ids):
        row = bp_map.get(str(asset.id))
        if row is None:
            out[_sk(asset.id)] = AssetBehavior(
                evidence=[orm_evidence(db, asset, source="soc_behavior_profiles")],
            )
            continue

        tag_names: list[str] = []
        if row.tags and isinstance(row.tags, list):
            for t in row.tags:
                if isinstance(t, dict) and "name" in t:
                    tag_names.append(t["name"])
        top_domain_count = len(row.top_domains) if row.top_domains else 0
        ueba = score_behavior_anomaly(row, asset_type=asset.asset_type)

        out[_sk(asset.id)] = AssetBehavior(
            profile_date=str(row.profile_date) if row.profile_date else None,
            traffic_type=row.traffic_type,
            status=row.status,
            total_visits=row.total or 0,
            top_domain_count=top_domain_count,
            tags=tag_names,
            layer_visit=row.layer_visit or {},
            anomaly_score=ueba.get("anomaly_score"),
            anomaly_signals=ueba.get("signals") or [],
            evidence=[orm_evidence(db, asset, source="soc_behavior_profiles")],
        )
    return out
