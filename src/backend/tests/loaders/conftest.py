"""OH-2.1 loaders 子包公共测试 fixture。

提供 ``sample_asset_for_profile`` + 关联表 seed，给 T2-T5 loader 测试共享。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from sqlalchemy.orm import Session

from app.models import (
    Asset, AssetPort, AssetBusiness, BusinessSystem, IdentityBinding,
    BehaviorProfile, ComplianceFinding,
)
from app.models.asset_risk import AssetRiskHistory
from app.models.asset_incident import AssetIncident
from app.models.vulnerability import AssetVulnerability, Vulnerability
from app.models.incident import Incident
from app.models.asset_source import AssetSource


NOW = datetime.now(timezone.utc)


@pytest.fixture
def sample_asset_for_profile(db_session: Session):
    """构造一帧覆盖 8 维的 Asset + 关联表 seed。

    覆盖：
    - identity: source_id (via AssetSource) + data_source + wazuh_agent_id + mac_address + IdentityBinding
    - ownership: owner + owner_contact + business_impact + business_systems
    - technology: os_name + open_ports_count + services
    - exposure: public_ip + exposure_level
    - vulnerability: risk_score + AssetVulnerability
    - threat: open_alerts (Incident open 状态)
    - compliance: data_classification + ComplianceFinding
    - behavior: BehaviorProfile（profile_date=today）
    """
    asset = Asset(
        network_segment="3F", asset_ip="192.168.1.100",
        asset_status="online", asset_type="server",
        data_source="wazuh",
        wazuh_agent_id="001",
        mac_address="aa:bb:cc:dd:ee:01",
        os_name="Ubuntu 22.04", os_version="5.15",
        hardware_info={"cpu": "Intel Xeon", "mem_gb": 32},
        public_ip="1.2.3.4", exposure_level="public",
        owner="张三", owner_contact="13800000000",
        business_unit="安全部",
        business_impact="core", data_sensitivity="high",
        protection_level="level_4",
        data_classification="confidential",
        name="prod-server-1",
        criticality="high",
        risk_score=72, risk_summary="存在暴露面高危",
        score_breakdown={"exposure": 50, "health": 30},
        created_at=NOW, updated_at=NOW,
    )
    db_session.add(asset)
    db_session.flush()

    # AssetSource（提供 source_id）
    db_session.add(AssetSource(
        asset_id=asset.id, source="wazuh", source_id="W-NET-001",
        source_status="active", last_seen_at=NOW,
    ))

    # IdentityBinding（提升 identity_confidence）
    ib = IdentityBinding(
        account="admin", ip="192.168.1.100", asset_id=asset.id,
        logins=10, first_seen=NOW, last_seen=NOW,
    )
    db_session.add(ib)

    # BusinessSystem + AssetBusiness
    bs = BusinessSystem(
        code="soc-platform", name="SOC 平台",
        business_impact="core", data_sensitivity="high",
        protection_level="level_4",
    )
    db_session.add(bs)
    db_session.flush()
    db_session.add(AssetBusiness(asset_id=asset.id, system_id=bs.id, role="app"))

    # Ports (open services)
    for port, service in [(22, "ssh"), (80, "nginx"), (443, "nginx")]:
        db_session.add(AssetPort(
            asset_id=asset.id, asset_ip=asset.asset_ip,
            port=port, protocol="tcp", state="open", service=service,
            scan_time=NOW,
        ))

    # Vulnerability + AssetVulnerability
    vuln = Vulnerability(
        type="cve", cve_id="CVE-2026-0001", severity="high", cvss_score=8.5,
        title="Test CVE", description="desc",
        published_date=NOW.date(), updated_at=NOW,
    )
    db_session.add(vuln)
    db_session.flush()
    db_session.add(AssetVulnerability(
        asset_id=asset.id, vulnerability_id=vuln.id,
        scanner="wazuh", status="open", detected_at=NOW,
    ))
    db_session.add(AssetRiskHistory(
        asset_id=asset.id, risk_score=72, score_breakdown={"exposure": 50},
        scored_at=NOW,
    ))

    # Incident + AssetIncident
    inc = Incident(
        title="Suspicious SSH", description="desc", status="open",
        severity="high", created_by="system", created_at=NOW, updated_at=NOW,
    )
    db_session.add(inc)
    db_session.flush()
    db_session.add(AssetIncident(asset_id=asset.id, incident_id=inc.id))

    # ComplianceFinding（latest run by asset）
    from app.models.compliance import ComplianceRun

    run = ComplianceRun(
        ruleset_version="v1", ruleset_name="base", rules_total=10,
        assets_total=1, assets_in_scope=1, pass_count=0, fail_count=1,
        unknown_count=0, compliance_rate=0, coverage_rate=100,
        stats={"assets": 1}, triggered_by="test",
    )
    db_session.add(run)
    db_session.flush()

    db_session.add(ComplianceFinding(
        asset_id=asset.id, run_id=run.id, rule_id="R001", rule_version=1, rule_title="Test rule",
        category="config", severity="high", status="fail",
        reason="desc",
        evidence=[{"source": "port_scan", "value": "22"}],
        created_at=NOW,
    ))

    # BehaviorProfile
    db_session.add(BehaviorProfile(
        asset_id=asset.id, ip=asset.asset_ip, profile_date=NOW.date(),
        status="ok", total=500, by_hour=[0]*24, by_block=[0]*7,
        layer_visit={"ACT": 0.6, "SYS": 0.3, "AD": 0.1},
        tags=[{"name": "研究型"}], top_domains=[],
        traffic_type="human", workday=400, weekend=100,
        generated_at=NOW,
    ))

    db_session.commit()
    db_session.refresh(asset)
    return asset


@pytest.fixture
def minimal_asset(db_session: Session):
    """最小 Asset（仅必填字段）。loader 应返回全空 dataclass。"""
    a = Asset(
        network_segment="default", asset_ip="192.168.1.200",
        asset_status="online",
        created_at=NOW, updated_at=NOW,
    )
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a