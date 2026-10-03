"""
OH-2.1 八维画像数据模型单元测试

覆盖：
- 8 dataclass 实例化 + frozen 不可变
- EvidenceItem confidence 范围校验
- CoverageInfo 8 维统计 + missing 列表
- profile_confidence 三档（全 / 部分 / 全空）
- profile_to_dict JSON-safe（datetime → ISO 8601 string）
- empty_profile 工厂 + 兜底
- DIMENSIONS 顺序冻结
"""
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, is_dataclass
from datetime import datetime, timedelta, timezone

import pytest

from app.services.asset_profile import (
    DIMENSIONS,
    AssetBehavior,
    AssetCompliance,
    AssetExposure,
    AssetIdentity,
    AssetOwnership,
    AssetProfile,
    AssetTechnology,
    AssetThreat,
    AssetVulnerability,
    CoverageInfo,
    EvidenceItem,
    compute_coverage,
    compute_profile_confidence,
    empty_profile,
    profile_to_dict,
)


NOW = datetime.now(timezone.utc)


def _ev(source: str = "soc_assets", conf: float = 0.9) -> EvidenceItem:
    return EvidenceItem(source=source, observed_at=NOW, confidence=conf)


# ---------------------------------------------------------------------------
# 1. 8 dataclass 实例化 + frozen
# ---------------------------------------------------------------------------


class TestDataclasses:
    @pytest.mark.parametrize(
        "cls",
        [
            AssetIdentity, AssetOwnership, AssetTechnology, AssetExposure,
            AssetVulnerability, AssetThreat, AssetCompliance, AssetBehavior,
        ],
    )
    def test_is_dataclass_and_frozen(self, cls):
        """8 个维 dataclass 必须 frozen + dataclass。"""
        assert is_dataclass(cls)
        # frozen 类应通过 __dataclass_params__.frozen 验证
        assert cls.__dataclass_params__.frozen is True
        # 构造实例后修改应抛 FrozenInstanceError
        if cls is AssetIdentity:
            inst = cls(source_id="x")
        elif cls is AssetOwnership:
            inst = cls(owner="x")
        elif cls is AssetTechnology:
            inst = cls()
        elif cls is AssetExposure:
            inst = cls()
        elif cls is AssetVulnerability:
            inst = cls()
        elif cls is AssetThreat:
            inst = cls()
        elif cls is AssetCompliance:
            inst = cls()
        elif cls is AssetBehavior:
            inst = cls()
        else:
            inst = cls()
        # 任意字段修改都应报 FrozenInstanceError
        with pytest.raises(FrozenInstanceError):
            inst.asset_id = "mutate"  # type: ignore[attr-defined]

    def test_identity_full(self):
        a = AssetIdentity(
            source_id="manual-1", data_source="manual", wazuh_agent_id="W01",
            mac_address="aa:bb:cc:dd:ee:ff", hostname="host-1",
            identity_confidence=0.85, identity_bindings_count=2,
            evidence=[_ev()],
        )
        assert a.source_id == "manual-1"
        assert a.identity_confidence == 0.85
        assert len(a.evidence) == 1

    def test_ownership_full(self):
        o = AssetOwnership(
            owner="张三", owner_contact="13800", business_unit="安全部",
            business_impact="core", data_sensitivity="high", protection_level="level_4",
            business_systems=["SOC"], business_system_codes=["soc-platform"],
            evidence=[_ev()],
        )
        assert o.owner == "张三"
        assert o.business_systems == ["SOC"]

    def test_technology_with_hardware(self):
        t = AssetTechnology(
            os_name="Ubuntu", os_version="22.04",
            hardware_info={"cpu": "Intel", "mem_gb": 16},
            open_ports_count=3, services=["ssh", "nginx"],
            components=["openssl 3.0"],  # SBOM 占位
            evidence=[_ev()],
        )
        assert t.hardware_info["cpu"] == "Intel"
        assert t.open_ports_count == 3

    def test_exposure_with_nat(self):
        e = AssetExposure(
            public_ip="1.2.3.4", exposure_level="public",
            nat_mapped_internal_ips=["192.168.1.10"],
            exposed_ports=[80, 443], wan_ip="5.6.7.8",
            evidence=[_ev("graph.maps_to")],
        )
        assert e.exposed_ports == [80, 443]
        assert e.wan_ip == "5.6.7.8"

    def test_vulnerability_breakdown(self):
        v = AssetVulnerability(
            risk_score=72, risk_summary="high", risk_scored_at=NOW,
            score_breakdown={"exposure": 50, "health": 30},
            vuln_total=5,
            vuln_by_severity={"critical": 1, "high": 2, "medium": 2},
            unfixed_high_count=2,
            evidence=[_ev("soc_asset_vulnerabilities")],
        )
        assert v.vuln_by_severity["critical"] == 1
        assert v.unfixed_high_count == 2

    def test_threat_with_attack_patterns(self):
        t = AssetThreat(
            open_alerts=3, highest_alert_level="high",
            recent_incident_count_30d=2,
            attack_patterns=["T1110", "T1078"],  # ATT&CK technique ids
            evidence=[_ev("soc_incidents")],
        )
        assert "T1110" in t.attack_patterns

    def test_compliance_with_3states(self):
        c = AssetCompliance(
            data_classification="confidential",
            compliance_pass_count=8, compliance_fail_count=2, compliance_unknown_count=1,
            last_compliance_run_at=NOW,
            ruleset_version="v1.2.0",
            evidence=[_ev("soc_compliance_findings")],
        )
        assert c.compliance_fail_count == 2
        assert c.ruleset_version == "v1.2.0"

    def test_behavior_full(self):
        b = AssetBehavior(
            profile_date="2026-10-03", traffic_type="human", status="ok",
            total_visits=1234, top_domain_count=10,
            tags=["研究型", "高频访问"],
            layer_visit={"ACT": 0.6, "SYS": 0.3, "AD": 0.1},
            evidence=[_ev("soc_behavior_profiles")],
        )
        assert b.total_visits == 1234
        assert b.layer_visit["ACT"] == 0.6


# ---------------------------------------------------------------------------
# 2. EvidenceItem 校验
# ---------------------------------------------------------------------------


class TestEvidenceItem:
    def test_valid_range(self):
        for conf in (0.0, 0.5, 1.0):
            EvidenceItem("soc_assets", NOW, conf)

    def test_out_of_range_raises(self):
        with pytest.raises(ValueError, match=r"confidence must be in"):
            EvidenceItem("soc_assets", NOW, 1.5)
        with pytest.raises(ValueError, match=r"confidence must be in"):
            EvidenceItem("soc_assets", NOW, -0.1)

    def test_optional_fields(self):
        e = EvidenceItem(
            source="ai_query", observed_at=NOW, confidence=0.7,
            reference="row 32", note="人工补录",
        )
        assert e.reference == "row 32"
        assert e.note == "人工补录"


# ---------------------------------------------------------------------------
# 3. compute_coverage
# ---------------------------------------------------------------------------


class TestComputeCoverage:
    def test_empty_profile(self):
        ep = empty_profile("a1")
        cov = compute_coverage(ep)
        assert cov.covered == 0
        assert cov.total == 8
        assert cov.ratio == 0.0
        assert set(cov.missing) == set(DIMENSIONS)

    def test_full_profile(self):
        p = AssetProfile(
            asset_id="full",
            identity=AssetIdentity(source_id="x", evidence=[_ev()]),
            ownership=AssetOwnership(owner="张三", evidence=[_ev()]),
            technology=AssetTechnology(os_name="Win", evidence=[_ev()]),
            exposure=AssetExposure(public_ip="1.2.3.4", evidence=[_ev()]),
            vulnerability=AssetVulnerability(risk_score=50, evidence=[_ev()]),
            threat=AssetThreat(open_alerts=3, evidence=[_ev()]),
            compliance=AssetCompliance(data_classification="internal", evidence=[_ev()]),
            behavior=AssetBehavior(profile_date="2026-10-03", evidence=[_ev()]),
        )
        cov = compute_coverage(p)
        assert cov.covered == 8
        assert cov.ratio == 1.0
        assert cov.missing == []

    def test_partial_profile(self):
        p = AssetProfile(
            asset_id="partial",
            identity=AssetIdentity(source_id="x", evidence=[_ev()]),
            ownership=AssetOwnership(owner="李四", evidence=[_ev()]),
            technology=AssetTechnology(os_name="Linux", evidence=[_ev()]),
        )
        cov = compute_coverage(p)
        assert cov.covered == 3
        assert cov.ratio == 0.375
        assert set(cov.missing) == {"exposure", "vulnerability", "threat", "compliance", "behavior"}

    def test_dimension_without_evidence_ignored(self):
        """evidence 为空时即使有字段也不算覆盖（避免误报）。"""
        p = AssetProfile(
            asset_id="no-ev",
            identity=AssetIdentity(source_id="x"),  # 无 evidence
            ownership=AssetOwnership(owner="z"),    # 无 evidence
        )
        cov = compute_coverage(p)
        assert cov.covered == 0


# ---------------------------------------------------------------------------
# 4. compute_profile_confidence
# ---------------------------------------------------------------------------


class TestComputeConfidence:
    def test_empty_returns_zero(self):
        assert compute_profile_confidence(empty_profile("a1")) == 0.0

    def test_full_high_confidence(self):
        ev = [_ev(conf=1.0)]
        p = AssetProfile(
            asset_id="full",
            identity=AssetIdentity(source_id="x", evidence=ev),
            ownership=AssetOwnership(owner="z", evidence=ev),
            technology=AssetTechnology(os_name="Win", evidence=ev),
            exposure=AssetExposure(public_ip="1.2.3.4", evidence=ev),
            vulnerability=AssetVulnerability(risk_score=50, evidence=ev),
            threat=AssetThreat(open_alerts=3, evidence=ev),
            compliance=AssetCompliance(data_classification="internal", evidence=ev),
            behavior=AssetBehavior(profile_date="2026-10-03", evidence=ev),
        )
        p = AssetProfile(
            asset_id=p.asset_id, identity=p.identity, ownership=p.ownership,
            technology=p.technology, exposure=p.exposure, vulnerability=p.vulnerability,
            threat=p.threat, compliance=p.compliance, behavior=p.behavior,
            coverage=compute_coverage(p),
        )
        assert compute_profile_confidence(p) == pytest.approx(1.0, abs=1e-3)

    def test_partial_low_confidence(self):
        ev = [_ev(conf=0.5)]
        p = AssetProfile(
            asset_id="partial",
            identity=AssetIdentity(source_id="x", evidence=ev),
            ownership=AssetOwnership(owner="z", evidence=ev),
            technology=AssetTechnology(os_name="Win", evidence=ev),
        )
        p = AssetProfile(
            asset_id=p.asset_id, identity=p.identity, ownership=p.ownership,
            technology=p.technology,
            coverage=compute_coverage(p),
        )
        # coverage=0.375 × dim_avg=0.5 = 0.1875
        assert compute_profile_confidence(p) == pytest.approx(0.1875, abs=1e-3)

    def test_coverage_but_no_evidence_returns_half(self):
        """覆盖但 evidence 全空时（理论上不应发生，因 _has_meaningful_data 已拦截），
        主动构造一个 fake coverage，验证降级到 0.5 折。"""
        p = AssetProfile(asset_id="fake")
        cov = CoverageInfo(covered=4, missing=[], ratio=0.5)
        p = AssetProfile(asset_id=p.asset_id, coverage=cov)
        assert compute_profile_confidence(p) == 0.25  # 0.5 × 0.5


# ---------------------------------------------------------------------------
# 5. profile_to_dict JSON-safe
# ---------------------------------------------------------------------------


class TestProfileToDict:
    def test_empty_serializable(self):
        d = profile_to_dict(empty_profile("a1"))
        # datetime → ISO string
        assert isinstance(d["built_at"], str)
        assert isinstance(d["coverage"]["covered"], int)
        # JSON safe: round-trip
        json_str = json.dumps(d, ensure_ascii=False)
        assert "asset_id" in json_str

    def test_full_serializable(self):
        p = AssetProfile(
            asset_id="full",
            identity=AssetIdentity(source_id="x", mac_address="aa:bb", evidence=[_ev()]),
            technology=AssetTechnology(os_name="Win", hardware_info={"cpu": "Intel"}, evidence=[_ev()]),
        )
        d = profile_to_dict(p)
        assert d["identity"]["mac_address"] == "aa:bb"
        assert d["technology"]["hardware_info"]["cpu"] == "Intel"
        assert isinstance(d["identity"]["evidence"][0]["observed_at"], str)

    def test_list_fields_serialized(self):
        b = AssetBehavior(
            profile_date="2026-10-03", tags=["A", "B"],
            layer_visit={"ACT": 0.6}, evidence=[_ev()],
        )
        p = AssetProfile(asset_id="x", behavior=b)
        d = profile_to_dict(p)
        assert d["behavior"]["tags"] == ["A", "B"]
        assert d["behavior"]["layer_visit"]["ACT"] == 0.6


# ---------------------------------------------------------------------------
# 6. empty_profile
# ---------------------------------------------------------------------------


class TestEmptyProfile:
    def test_all_dimensions_empty(self):
        p = empty_profile("a1")
        assert p.asset_id == "a1"
        assert p.identity == AssetIdentity()
        assert p.ownership == AssetOwnership()
        assert p.technology == AssetTechnology()
        assert p.exposure == AssetExposure()
        assert p.vulnerability == AssetVulnerability()
        assert p.threat == AssetThreat()
        assert p.compliance == AssetCompliance()
        assert p.behavior == AssetBehavior()
        assert p.ahs_score == 0
        assert p.ahs_evidence == []
        assert p.profile_confidence == 0.0

    def test_coverage_zero(self):
        cov = compute_coverage(empty_profile("a1"))
        assert cov.ratio == 0.0


# ---------------------------------------------------------------------------
# 7. DIMENSIONS 顺序冻结
# ---------------------------------------------------------------------------


class TestDimensions:
    def test_dimensions_order(self):
        """八维顺序必须与主方案 §3.2 + 跟踪表一致。"""
        assert DIMENSIONS == (
            "identity", "ownership", "technology", "exposure",
            "vulnerability", "threat", "compliance", "behavior",
        )

    def test_dimensions_length(self):
        assert len(DIMENSIONS) == 8


# ---------------------------------------------------------------------------
# 8. CoverageInfo 工厂
# ---------------------------------------------------------------------------


class TestCoverageInfo:
    def test_defaults(self):
        c = CoverageInfo()
        assert c.total == 8
        assert c.covered == 0
        assert c.missing == []
        assert c.ratio == 0.0

    def test_with_values(self):
        c = CoverageInfo(
            covered=5,
            missing=["behavior", "compliance", "threat"],
            ratio=0.625,
        )
        assert c.covered == 5
        assert len(c.missing) == 3


# ---------------------------------------------------------------------------
# 9. AssetProfile AHS 占位
# ---------------------------------------------------------------------------


class TestAHSPlaceholder:
    def test_ahs_default_zero(self):
        p = AssetProfile(asset_id="x")
        assert p.ahs_score == 0
        assert p.ahs_evidence == []
        assert p.ahs_computed_at is None

    def test_ahs_can_be_set(self):
        ev = _ev()
        p = AssetProfile(
            asset_id="x", ahs_score=72, ahs_evidence=[ev],
            ahs_computed_at=NOW,
        )
        assert p.ahs_score == 72
        assert len(p.ahs_evidence) == 1
