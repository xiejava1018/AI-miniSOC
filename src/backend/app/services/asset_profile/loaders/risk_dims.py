"""OH-2.1 T4 — ④ 暴露维 + ⑤ 脆弱维 + ⑥ 威胁维 loader。

数据来源：
- 暴露：``soc_assets`` (public_ip/exposure_level) + ``soc_asset_ports`` (exposed_ports)
- 脆弱：``soc_assets`` (risk_score/score_breakdown) + ``soc_asset_vulnerabilities`` (vuln_total/by_severity)
- 威胁：``soc_asset_incidents`` + ``soc_incidents``（open_alerts/highest_level/recent_30d）
       + ATT&CK feed（OH-4.4 占位，当前为空列表）
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Asset, AssetPort, AssetIncident
from app.models.vulnerability import AssetVulnerability as ORMAssetVulnerability, Vulnerability
from app.models.incident import Incident
from app.services.asset_profile._main import (
    AssetExposure,
    AssetVulnerability,
    AssetThreat,
)
from app.services.asset_profile._helpers import orm_evidence, safe_load


@safe_load(default=AssetExposure())
def load_exposure(db: Session, asset: Asset) -> AssetExposure:
    """④ 暴露维：从 Asset + AssetPort 聚合 public_ip + 暴露端口。

    注：NAT 推导（OH-3.4）+ 图谱 maps_to 边整合在 OH-3.x；
    本任务只取 ``soc_assets`` 直接字段 + 端口表 state=open 的端口。
    """
    exposed_ports = []
    if asset.public_ip:
        ports = db.execute(
            select(AssetPort.port)
            .where(AssetPort.asset_id == asset.id, AssetPort.state == "open")
            .order_by(AssetPort.port)
        ).all()
        exposed_ports = [p.port for p in ports]

    evidence = [orm_evidence(db, asset, source="soc_assets")]

    return AssetExposure(
        public_ip=asset.public_ip,
        exposure_level=asset.exposure_level,
        nat_mapped_internal_ips=[],   # OH-3.4 后续填充
        exposed_ports=exposed_ports,
        wan_ip=None,                  # WAN IP 由 OH-3.4 从 TP-Link NAT 表填充
        evidence=evidence,
    )


@safe_load(default=AssetVulnerability())
def load_vulnerability(db: Session, asset: Asset) -> AssetVulnerability:
    """⑤ 脆弱维：从 Asset + AssetVulnerability 聚合 risk_score + 漏洞分档。"""
    # 漏洞按 severity 分档
    rows = db.execute(
        select(Vulnerability.severity, func.count(ORMAssetVulnerability.id))
        .join(ORMAssetVulnerability, ORMAssetVulnerability.vulnerability_id == Vulnerability.id)
        .where(ORMAssetVulnerability.asset_id == asset.id)
        .group_by(Vulnerability.severity)
    ).all()
    vuln_by_severity = {r.severity: r[1] for r in rows}
    vuln_total = sum(vuln_by_severity.values())

    # 未修复高危：severity in (high, critical) AND status=open
    unfixed_high = db.scalar(
        select(func.count(ORMAssetVulnerability.id))
        .join(Vulnerability, Vulnerability.id == ORMAssetVulnerability.vulnerability_id)
        .where(
            ORMAssetVulnerability.asset_id == asset.id,
            ORMAssetVulnerability.status == "open",
            Vulnerability.severity.in_(["critical", "high"]),
        )
    ) or 0

    evidence = [
        orm_evidence(db, asset, source="soc_assets"),
        orm_evidence(db, asset, source="soc_asset_vulnerabilities"),
    ]

    return AssetVulnerability(
        risk_score=asset.risk_score,
        risk_summary=asset.risk_summary,
        risk_scored_at=asset.risk_scored_at,
        score_breakdown=asset.score_breakdown or {},
        vuln_total=vuln_total,
        vuln_by_severity=vuln_by_severity,
        unfixed_high_count=unfixed_high,
        evidence=evidence,
    )


@safe_load(default=AssetThreat())
def load_threat(db: Session, asset: Asset) -> AssetThreat:
    """⑥ 威胁维：从 AssetIncident + Incident 聚合 open_alerts + highest + recent_30d。

    等级映射：Incident.severity (critical/high/medium/low) → 直传 highest_alert_level
    """
    # open_alerts + highest_level
    open_rows = db.execute(
        select(Incident.severity, func.count(Incident.id))
        .join(AssetIncident, AssetIncident.incident_id == Incident.id)
        .where(AssetIncident.asset_id == asset.id, Incident.status == "open")
        .group_by(Incident.severity)
    ).all()
    open_alerts = sum(r[1] for r in open_rows)
    severity_rank = {"critical": 4, "high": 3, "medium": 2, "low": 1}
    highest = None
    if open_rows:
        highest = max(open_rows, key=lambda r: severity_rank.get(r.severity, 0))[0]

    # recent_30d 事件数（基于 created_at，非 status）
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    recent_30d = db.scalar(
        select(func.count(Incident.id))
        .join(AssetIncident, AssetIncident.incident_id == Incident.id)
        .where(
            AssetIncident.asset_id == asset.id,
            Incident.created_at >= cutoff,
        )
    ) or 0

    evidence = [orm_evidence(db, asset, source="soc_incidents")]

    return AssetThreat(
        open_alerts=open_alerts,
        highest_alert_level=highest,
        recent_incident_count_30d=recent_30d,
        attack_patterns=[],  # OH-4.4 占位：ATT&CK STIX feed 导入后填充
        evidence=evidence,
    )