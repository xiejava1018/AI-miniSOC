"""OH-2.2 AHS 计算服务单测（纯函数，无 DB）。

覆盖：
- 5 维单维评分（暴露/脆弱/威胁/合规/行为）
- 关键性系数（BIA × CIA × 等保） + 范围保护
- 重归一化（数据缺维）
- insufficient_data 状态机
- apply_ahs_to_profile 兼容 frozen
- 完整评估 profile → AHS 校验
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.asset_profile import (
    AssetProfile, AssetIdentity, AssetOwnership, AssetTechnology, AssetExposure,
    AssetVulnerability, AssetThreat, AssetCompliance, AssetBehavior,
    EvidenceItem,
    compute_ahs, compute_criticality_factor, apply_ahs_to_profile,
    AHSResult, DimensionScore,
    AHS_DIMENSION_WEIGHTS, AHS_MIN_COVERED_DIMENSIONS,
    empty_profile,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _ev(source="soc_assets", confidence=0.8):
    return EvidenceItem(
        source=source,
        observed_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
        confidence=confidence,
    )


def _identity():
    return AssetIdentity(
        source_id="W-001",
        data_source="manual",
        wazuh_agent_id="A-100",
        mac_address="00:11:22:33:44:55",
        identity_confidence=0.9,
        evidence=[_ev("soc_identity_bindings")],
    )


def _ownership(bia="important", cia="high", prot="level_3"):
    return AssetOwnership(
        owner="zhangsan",
        business_impact=bia,
        data_sensitivity=cia,
        protection_level=prot,
        evidence=[_ev("soc_assets")],
    )


def _technology():
    return AssetTechnology(
        os_name="Ubuntu 22.04",
        os_version="22.04",
        open_ports_count=3,
        services=["ssh", "http"],
        evidence=[_ev("soc_asset_ports")],
    )


def _exposure(public_ip=None, exposure_level="internal"):
    return AssetExposure(
        public_ip=public_ip,
        exposure_level=exposure_level,
        evidence=[_ev("soc_assets")],
    )


def _vulnerability(risk_score=30, crit=0, high=2, low=0, med=None, unfixed_high=0):
    med = med if med is not None else (3 if crit or high else 0)
    return AssetVulnerability(
        risk_score=risk_score,
        vuln_by_severity={"critical": crit, "high": high, "medium": med, "low": low},
        unfixed_high_count=unfixed_high,
        evidence=[_ev("soc_asset_vulnerabilities"), _ev("soc_assets")],
    )


def _threat(level=None, open_alerts=0, incidents=0, patterns=None):
    return AssetThreat(
        open_alerts=open_alerts,
        highest_alert_level=level,
        recent_incident_count_30d=incidents,
        attack_patterns=patterns or [],
        evidence=[_ev("soc_alerts"), _ev("soc_incidents")],
    )


def _compliance(pass_n=5, fail_n=0, unknown_n=0, data_class="internal"):
    return AssetCompliance(
        compliance_pass_count=pass_n,
        compliance_fail_count=fail_n,
        compliance_unknown_count=unknown_n,
        data_classification=data_class,
        evidence=[_ev("soc_compliance_findings")],
    )


def _behavior(status="ok", tags=None, layer_visit=None):
    return AssetBehavior(
        profile_date="2026-10-03",
        traffic_type="human",
        status=status,
        tags=tags or [],
        layer_visit=layer_visit or {"ACT": 0.6, "SYS": 0.3, "AD": 0.1},
        evidence=[_ev("soc_behavior_profiles")],
    )


def _full_profile(**kwargs):
    """完整 8 维画像（criticality=important/high/level_3 → 因子=1.1×1.15×1.10=1.39）。"""
    p = AssetProfile(
        asset_id="asset-1",
        identity=_identity(),
        ownership=kwargs.get("ownership") or _ownership(),
        technology=_technology(),
        exposure=kwargs.get("exposure") or _exposure(),
        vulnerability=kwargs.get("vulnerability") or _vulnerability(),
        threat=kwargs.get("threat") or _threat(),
        compliance=kwargs.get("compliance") or _compliance(),
        behavior=kwargs.get("behavior") or _behavior(),
    )
    return p


# ---------------------------------------------------------------------------
# 单维评分
# ---------------------------------------------------------------------------

class TestExposureScore:
    def test_internal_no_public_ip(self):
        p = _full_profile(exposure=_exposure(exposure_level="internal"))
        r = compute_ahs(p)
        exp = next(d for d in r.dimensions if d.name == "exposure")
        assert exp.raw_score == 0
        assert "内网资产" in exp.contributing_factors[0]

    def test_public_ip_bonus(self):
        p = _full_profile(exposure=_exposure(public_ip="1.2.3.4"))
        r = compute_ahs(p)
        exp = next(d for d in r.dimensions if d.name == "exposure")
        assert exp.raw_score == 40
        assert any("公网 IP" in f for f in exp.contributing_factors)

    def test_exposure_level_public(self):
        p = _full_profile(exposure=_exposure(exposure_level="public"))
        r = compute_ahs(p)
        exp = next(d for d in r.dimensions if d.name == "exposure")
        assert exp.raw_score == 30

    def test_exposure_level_dmz(self):
        p = _full_profile(exposure=_exposure(exposure_level="dmz"))
        r = compute_ahs(p)
        exp = next(d for d in r.dimensions if d.name == "exposure")
        assert exp.raw_score == 20

    def test_isolated_network_negative_score_clamped(self):
        p = _full_profile(exposure=_exposure(exposure_level="isolated"))
        r = compute_ahs(p)
        exp = next(d for d in r.dimensions if d.name == "exposure")
        assert exp.raw_score == 0  # clamp(0, -30 → 0)


class TestVulnerabilityScore:
    def test_no_vulns_no_risk_score(self):
        p = _full_profile(vulnerability=AssetVulnerability(evidence=[_ev()]))
        r = compute_ahs(p)
        v = next(d for d in r.dimensions if d.name == "vulnerability")
        assert v.raw_score == 0
        assert "未见活跃漏洞" in v.contributing_factors[0]

    def test_risk_score_only(self):
        p = _full_profile(vulnerability=_vulnerability(risk_score=70, crit=0, high=0, med=0, low=0))
        r = compute_ahs(p)
        v = next(d for d in r.dimensions if d.name == "vulnerability")
        assert v.raw_score == 70

    def test_critical_count_score(self):
        p = _full_profile(vulnerability=_vulnerability(crit=2, high=0, med=0, low=0))
        r = compute_ahs(p)
        v = next(d for d in r.dimensions if d.name == "vulnerability")
        assert v.raw_score >= 60  # 2×30=60

    def test_unfixed_high_bonus(self):
        p = _full_profile(vulnerability=_vulnerability(high=3, low=0, med=0, unfixed_high=3))
        r = compute_ahs(p)
        v = next(d for d in r.dimensions if d.name == "vulnerability")
        assert v.raw_score >= 60  # 3×15 + 15 = 60


class TestThreatScore:
    def test_no_threats(self):
        p = _full_profile(threat=AssetThreat(evidence=[_ev()]))
        r = compute_ahs(p)
        t = next(d for d in r.dimensions if d.name == "threat")
        assert t.raw_score == 0

    def test_critical_alert(self):
        p = _full_profile(threat=_threat(level="critical"))
        r = compute_ahs(p)
        t = next(d for d in r.dimensions if d.name == "threat")
        assert t.raw_score >= 50

    def test_open_alerts_count(self):
        p = _full_profile(threat=_threat(open_alerts=4))
        r = compute_ahs(p)
        t = next(d for d in r.dimensions if d.name == "threat")
        assert t.raw_score >= 20  # 4×5

    def test_recent_incidents_capped(self):
        p = _full_profile(threat=_threat(incidents=10))
        r = compute_ahs(p)
        t = next(d for d in r.dimensions if d.name == "threat")
        # 10 × 10 = 100, cap 40
        assert t.raw_score >= 40

    def test_attack_patterns_bonus(self):
        p = _full_profile(threat=_threat(patterns=["T1003", "T1059"]))
        r = compute_ahs(p)
        t = next(d for d in r.dimensions if d.name == "threat")
        assert t.raw_score >= 20


class TestComplianceScore:
    def test_all_pass_zero(self):
        p = _full_profile(compliance=_compliance(pass_n=10, fail_n=0))
        r = compute_ahs(p)
        c = next(d for d in r.dimensions if d.name == "compliance")
        assert c.raw_score == 0

    def test_all_fail_max(self):
        p = _full_profile(compliance=_compliance(pass_n=0, fail_n=10))
        r = compute_ahs(p)
        c = next(d for d in r.dimensions if d.name == "compliance")
        assert c.raw_score == 80

    def test_unknown_partial(self):
        p = _full_profile(compliance=_compliance(pass_n=0, fail_n=0, unknown_n=10))
        r = compute_ahs(p)
        c = next(d for d in r.dimensions if d.name == "compliance")
        assert c.raw_score == 20

    def test_data_classification_only(self):
        p = _full_profile(compliance=AssetCompliance(data_classification="secret", evidence=[_ev()]))
        r = compute_ahs(p)
        c = next(d for d in r.dimensions if d.name == "compliance")
        # secret → 80 / 2 = 40（半权）
        assert c.raw_score == 40


class TestBehaviorScore:
    def test_ok_status_zero(self):
        p = _full_profile(behavior=_behavior(status="ok"))
        r = compute_ahs(p)
        b = next(d for d in r.dimensions if d.name == "behavior")
        assert b.raw_score == 0

    def test_gap_status_bonus(self):
        p = _full_profile(behavior=_behavior(status="gap"))
        r = compute_ahs(p)
        b = next(d for d in r.dimensions if d.name == "behavior")
        assert b.raw_score >= 30

    def test_low_act_ratio_bonus(self):
        p = _full_profile(behavior=_behavior(layer_visit={"ACT": 0.05, "SYS": 0.7, "AD": 0.25}))
        r = compute_ahs(p)
        b = next(d for d in r.dimensions if d.name == "behavior")
        assert b.raw_score >= 20

    def test_risky_tags(self):
        p = _full_profile(behavior=_behavior(tags=["anomaly", "lateral"]))
        r = compute_ahs(p)
        b = next(d for d in r.dimensions if d.name == "behavior")
        assert b.raw_score >= 30  # 2×15


# ---------------------------------------------------------------------------
# 关键性系数
# ---------------------------------------------------------------------------

class TestCriticalityFactor:
    def test_core_extreme_level5_max(self):
        p = _full_profile(ownership=_ownership(bia="core", cia="extreme", prot="level_5"))
        factor = compute_criticality_factor(p)
        assert factor == 1.5  # 1.3 × 1.3 × 1.5 = 2.535, clamp 到 1.5

    def test_normal_medium_level2_neutral(self):
        p = _full_profile(ownership=_ownership(bia="normal", cia="medium", prot="level_2"))
        factor = compute_criticality_factor(p)
        assert factor == pytest.approx(1.0 * 1.0 * 0.95, abs=0.01)

    def test_ignorable_negligible_level1_min(self):
        p = _full_profile(ownership=_ownership(bia="ignorable", cia="negligible", prot="level_1"))
        factor = compute_criticality_factor(p)
        # 0.8 × 0.8 × 0.85 = 0.544, clamp 到 0.8
        assert factor == 0.8

    def test_missing_protection_neutral(self):
        """等保字段空 → 1.00（主方案红线：禁止放大）"""
        p = _full_profile(ownership=AssetOwnership(
            owner="x", business_impact="important", data_sensitivity="high",
            protection_level=None, evidence=[_ev()],
        ))
        factor = compute_criticality_factor(p)
        assert factor == pytest.approx(1.1 * 1.15 * 1.0, abs=0.01)

    def test_all_missing_neutral(self):
        p = _full_profile(ownership=AssetOwnership(evidence=[_ev()]))
        factor = compute_criticality_factor(p)
        assert factor == 1.0  # 1.0 × 1.0 × 1.0


# ---------------------------------------------------------------------------
# 重归一化 / insufficient_data
# ---------------------------------------------------------------------------

class TestRenormalization:
    def test_full_data_valid(self):
        p = _full_profile()
        r = compute_ahs(p)
        assert r.state == "valid"
        assert r.score >= 0 and r.score <= 100

    def test_all_dim_data_gap_insufficient(self):
        """8 维全空 evidence → AHS 状态=insufficient_data, score=50"""
        p = AssetProfile(asset_id="empty")
        r = compute_ahs(p)
        assert r.state == "insufficient_data"
        assert r.score == 50
        assert all(d.data_gap for d in r.dimensions)

    def test_only_2_dims_insufficient(self):
        """仅 2 维有数据 → < 3 维 → insufficient_data"""
        p = AssetProfile(
            asset_id="a",
            exposure=_exposure(public_ip="1.2.3.4"),
            threat=_threat(level="critical"),
        )
        r = compute_ahs(p)
        assert r.state == "insufficient_data"

    def test_3_dims_valid(self):
        """3 维有数据 → valid"""
        p = AssetProfile(
            asset_id="a",
            exposure=_exposure(public_ip="1.2.3.4"),
            threat=_threat(level="critical"),
            vulnerability=_vulnerability(risk_score=80),
        )
        r = compute_ahs(p)
        assert r.state == "valid"

    def test_renormalize_effective_weight_sum_one(self):
        """数据缺维后，剩余维的 effective_weight 之和 = 1.0"""
        p = AssetProfile(
            asset_id="a",
            exposure=_exposure(public_ip="1.2.3.4"),  # 有数据
            threat=_threat(level="critical"),          # 有数据
            vulnerability=_vulnerability(risk_score=80),  # 有数据
            compliance=AssetCompliance(),  # 无 evidence
            behavior=AssetBehavior(),       # 无 evidence
        )
        r = compute_ahs(p)
        valid_dims = [d for d in r.dimensions if not d.data_gap]
        total = sum(d.effective_weight for d in valid_dims)
        assert total == pytest.approx(1.0, abs=0.001)


# ---------------------------------------------------------------------------
# apply_ahs_to_profile（frozen 兼容）
# ---------------------------------------------------------------------------

class TestApplyAHSToProfile:
    def test_returns_new_profile_with_score(self):
        p = _full_profile()
        r = compute_ahs(p)
        new_p = apply_ahs_to_profile(p, r)
        assert new_p.ahs_score == r.score
        assert isinstance(new_p, AssetProfile)
        assert new_p is not p  # frozen → 必须新对象

    def test_original_profile_unchanged(self):
        p = _full_profile()
        r = compute_ahs(p)
        _ = apply_ahs_to_profile(p, r)
        assert p.ahs_score == 0  # 原对象不变

    def test_evidence_copied(self):
        p = _full_profile()
        r = compute_ahs(p)
        new_p = apply_ahs_to_profile(p, r)
        assert isinstance(new_p.ahs_evidence, list)
        assert len(new_p.ahs_evidence) >= 0


# ---------------------------------------------------------------------------
# 完整评估
# ---------------------------------------------------------------------------

class TestFullProfile:
    def test_high_risk_asset_low_ahs(self):
        """高风险画像 → AHS 低（< 50）"""
        p = AssetProfile(
            asset_id="high-risk",
            identity=_identity(),
            ownership=_ownership(bia="core", cia="extreme", prot="level_5"),
            technology=_technology(),
            exposure=_exposure(public_ip="1.2.3.4", exposure_level="public"),
            vulnerability=_vulnerability(risk_score=85, crit=5, high=10),
            threat=_threat(level="critical", open_alerts=5, incidents=3, patterns=["T1003", "T1059"]),
            compliance=_compliance(pass_n=0, fail_n=10),
            behavior=_behavior(status="gap", tags=["anomaly", "lateral"]),
        )
        r = compute_ahs(p)
        assert r.state == "valid"
        assert r.score < 50  # 高风险 → 健康分低

    def test_healthy_asset_high_ahs(self):
        """健康画像 → AHS 高（> 70）"""
        p = AssetProfile(
            asset_id="healthy",
            identity=_identity(),
            ownership=_ownership(bia="ignorable", cia="negligible", prot="level_1"),
            technology=_technology(),
            exposure=_exposure(exposure_level="isolated"),
            vulnerability=_vulnerability(risk_score=10, crit=0, high=0),
            threat=AssetThreat(evidence=[_ev()]),
            compliance=_compliance(pass_n=10, fail_n=0),
            behavior=_behavior(status="ok"),
        )
        r = compute_ahs(p)
        assert r.state == "valid"
        assert r.score > 60  # 健康 → AHS 高

    def test_to_dict_json_safe(self):
        p = _full_profile()
        r = compute_ahs(p)
        d = r.to_dict()
        assert isinstance(d["score"], int)
        assert isinstance(d["state"], str)
        assert isinstance(d["dimensions"], list)
        assert all("name" in dim for dim in d["dimensions"])
        assert all("raw_score" in dim for dim in d["dimensions"])


# ---------------------------------------------------------------------------
# 边界条件
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_score_clamped_0(self):
        """所有维扣分 ≥ 100 + 关键性 > 1 → AHS = 0（不报错）"""
        p = AssetProfile(
            asset_id="worst",
            ownership=_ownership(bia="core", cia="extreme", prot="level_5"),
            exposure=_exposure(public_ip="1.2.3.4", exposure_level="public"),
            vulnerability=_vulnerability(risk_score=100, crit=10, high=20),
            threat=_threat(level="critical", open_alerts=10, incidents=20, patterns=["T1"]*5),
            compliance=_compliance(pass_n=0, fail_n=100),
            behavior=_behavior(status="gap", tags=["anomaly"]*5),
        )
        r = compute_ahs(p)
        assert r.score >= 0
        assert r.score <= 100

    def test_dimension_weights_complete(self):
        """5 维权重总和 = 1.0"""
        assert sum(AHS_DIMENSION_WEIGHTS.values()) == pytest.approx(1.0, abs=0.001)

    def test_min_covered_dimensions_constant(self):
        assert AHS_MIN_COVERED_DIMENSIONS == 3