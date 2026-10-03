"""OH-2.1 T4 — ④ 暴露维 + ⑤ 脆弱维 + ⑥ 威胁维 loader 单测。"""
from __future__ import annotations

from app.services.asset_profile import (
    AssetExposure, AssetVulnerability, AssetThreat,
)
from app.services.asset_profile.loaders.risk_dims import (
    load_exposure, load_vulnerability, load_threat,
)


class TestLoadExposure:
    """T4 — ④ 暴露维 loader 单测（3 例）。"""

    def test_full_seeded_returns_public_ip_and_ports(self, db_session, sample_asset_for_profile):
        """完整 seed（public_ip=1.2.3.4 + 3 端口）→ 暴露端口填入。"""
        result = load_exposure(db_session, sample_asset_for_profile)
        assert isinstance(result, AssetExposure)
        assert result.public_ip == "1.2.3.4"
        assert result.exposure_level == "public"
        assert sorted(result.exposed_ports) == [22, 80, 443]

    def test_minimal_asset_no_public_ip(self, db_session, minimal_asset):
        """最小 asset（无 public_ip）→ exposed_ports=[], nat 字段空。"""
        result = load_exposure(db_session, minimal_asset)
        assert isinstance(result, AssetExposure)
        assert result.public_ip is None
        assert result.exposed_ports == []
        assert result.nat_mapped_internal_ips == []
        assert result.wan_ip is None

    def test_evidence_attached(self, db_session, sample_asset_for_profile):
        """evidence.source = soc_assets。"""
        result = load_exposure(db_session, sample_asset_for_profile)
        assert len(result.evidence) >= 1
        assert result.evidence[0].source == "soc_assets"


class TestLoadVulnerability:
    """T4 — ⑤ 脆弱维 loader 单测（3 例）。"""

    def test_full_seeded_returns_risk_score_and_vulns(self, db_session, sample_asset_for_profile):
        """完整 seed（risk_score=72 + 1 high CVE）→ 漏洞分档 + unfixed_high。"""
        result = load_vulnerability(db_session, sample_asset_for_profile)
        assert isinstance(result, AssetVulnerability)
        assert result.risk_score == 72
        assert result.vuln_total == 1
        assert result.vuln_by_severity.get("high") == 1
        assert result.unfixed_high_count == 1
        # score_breakdown 是 dict
        assert isinstance(result.score_breakdown, dict)

    def test_minimal_asset_no_vulns(self, db_session, minimal_asset):
        """最小 asset → vuln_total=0, unfixed_high=0, risk_score=None。"""
        result = load_vulnerability(db_session, minimal_asset)
        assert isinstance(result, AssetVulnerability)
        assert result.risk_score is None
        assert result.vuln_total == 0
        assert result.vuln_by_severity == {}
        assert result.unfixed_high_count == 0

    def test_evidence_two_sources(self, db_session, sample_asset_for_profile):
        """evidence 来自 soc_assets + soc_asset_vulnerabilities 两表。"""
        result = load_vulnerability(db_session, sample_asset_for_profile)
        sources = {ev.source for ev in result.evidence}
        assert "soc_assets" in sources
        assert "soc_asset_vulnerabilities" in sources


class TestLoadThreat:
    """T4 — ⑥ 威胁维 loader 单测（3 例）。"""

    def test_full_seeded_open_incident(self, db_session, sample_asset_for_profile):
        """完整 seed（1 open high 事件）→ open_alerts=1, highest=high。"""
        result = load_threat(db_session, sample_asset_for_profile)
        assert isinstance(result, AssetThreat)
        assert result.open_alerts == 1
        assert result.highest_alert_level == "high"
        assert result.recent_incident_count_30d == 1
        assert result.attack_patterns == []  # OH-4.4 占位

    def test_minimal_asset_no_incidents(self, db_session, minimal_asset):
        """最小 asset → open_alerts=0, highest=None, recent_30d=0。"""
        result = load_threat(db_session, minimal_asset)
        assert isinstance(result, AssetThreat)
        assert result.open_alerts == 0
        assert result.highest_alert_level is None
        assert result.recent_incident_count_30d == 0

    def test_closed_incident_not_counted(self, db_session, sample_asset_for_profile):
        """closed 事件不计入 open_alerts（但仍计入 recent_30d）。"""
        from app.models import Incident, AssetIncident
        from datetime import datetime, timezone

        # 把已有 incident 标记 closed
        inc = db_session.query(Incident).first()
        assert inc is not None
        inc.status = "closed"
        inc.updated_at = datetime.now(timezone.utc)
        db_session.commit()

        result = load_threat(db_session, sample_asset_for_profile)
        assert result.open_alerts == 0
        assert result.highest_alert_level is None
        assert result.recent_incident_count_30d == 1  # recent 不受 status 影响