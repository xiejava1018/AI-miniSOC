"""OH-UI.4 完整度评分卡 API 单测。

覆盖：
- _assemble_response 组装函数（纯函数，无 DB 依赖）
- 八维明细聚合
- coverage ratio 计算
- state 状态机（valid / insufficient_data / partial / error）
- evidence_summary 透传
- 集成测试：build_profile → compute_ahs → apply_ahs → build_evidence_chain → _assemble_response
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.asset_profile import (
    AssetProfile, AssetIdentity, AssetOwnership, AssetTechnology, AssetExposure,
    AssetVulnerability, AssetThreat, AssetCompliance, AssetBehavior,
    EvidenceItem,
    compute_ahs, apply_ahs_to_profile, build_evidence_chain,
)
from app.api.asset_completeness import _assemble_response

DAY = datetime(2026, 10, 3, tzinfo=timezone.utc)


def _ev(source="soc_assets", days_offset=0, confidence=0.8):
    return EvidenceItem(
        source=source,
        observed_at=DAY + timedelta(days=days_offset),
        confidence=confidence,
    )


def _profile_full():
    """完整 8 维画像。"""
    ev = _ev(source="soc_assets", confidence=0.9)
    return AssetProfile(
        asset_id="asset-1",
        identity=AssetIdentity(source_id="W-001", evidence=[ev]),
        ownership=AssetOwnership(
            owner="zhangsan",
            business_impact="important",
            data_sensitivity="high",
            protection_level="level_3",
            evidence=[ev],
        ),
        technology=AssetTechnology(os_name="Ubuntu 22.04", evidence=[ev]),
        exposure=AssetExposure(public_ip="1.2.3.4", evidence=[ev]),
        vulnerability=AssetVulnerability(risk_score=70, evidence=[ev]),
        threat=AssetThreat(highest_alert_level="critical", evidence=[ev]),
        compliance=AssetCompliance(compliance_fail_count=3, evidence=[ev]),
        behavior=AssetBehavior(profile_date="2026-10-03", evidence=[ev]),
    )


def _profile_partial(covered_dims: set[str]):
    """仅 covered_dims 有 evidence。"""
    ev = _ev(source="soc_assets", confidence=0.8)
    kwargs = {"asset_id": "asset-2"}
    if "identity" in covered_dims:
        kwargs["identity"] = AssetIdentity(source_id="X", evidence=[ev])
    if "ownership" in covered_dims:
        kwargs["ownership"] = AssetOwnership(owner="y", evidence=[ev])
    if "technology" in covered_dims:
        kwargs["technology"] = AssetTechnology(os_name="Linux", evidence=[ev])
    if "exposure" in covered_dims:
        kwargs["exposure"] = AssetExposure(public_ip="1.2.3.4", evidence=[ev])
    if "vulnerability" in covered_dims:
        kwargs["vulnerability"] = AssetVulnerability(risk_score=50, evidence=[ev])
    if "threat" in covered_dims:
        kwargs["threat"] = AssetThreat(highest_alert_level="high", evidence=[ev])
    if "compliance" in covered_dims:
        kwargs["compliance"] = AssetCompliance(compliance_pass_count=5, evidence=[ev])
    if "behavior" in covered_dims:
        kwargs["behavior"] = AssetBehavior(profile_date="2026-10-03", evidence=[ev])
    return AssetProfile(**kwargs)


def _profile_empty():
    return AssetProfile(asset_id="empty")


# ---------------------------------------------------------------------------
# _assemble_response 基本组装
# ---------------------------------------------------------------------------

class TestAssembleBasic:
    def test_full_profile_assembles(self):
        p = _profile_full()
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)

        resp = _assemble_response(p_with_ahs, ahs, chain)
        assert resp["asset_id"] == "asset-1"
        assert resp["state"] == "valid"
        assert resp["ahs_state"] == "valid"
        assert resp["ahs_score"] == ahs.score
        assert resp["overall_score"] == 100  # 8/8 覆盖
        assert resp["coverage"]["total"] == 8
        assert resp["coverage"]["covered"] == 8
        assert resp["coverage"]["missing"] == 0
        assert resp["coverage"]["ratio"] == 1.0

    def test_empty_profile(self):
        p = _profile_empty()
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)

        resp = _assemble_response(p_with_ahs, ahs, chain)
        assert resp["state"] == "insufficient_data"
        assert resp["overall_score"] == 0
        assert resp["coverage"]["covered"] == 0
        assert resp["ahs_score"] == 50  # insufficient_data 默认值

    def test_partial_3_dims_valid(self):
        """3 维均有数据（evidence + 核心字段）→ AHS valid → 但 8 维覆盖 3/8 = partial state
        **双重含义**：overall_score = 3/8 完整度低，但 AHS valid（评 5 维口径有 3 维）
        """
        p = AssetProfile(
            asset_id="test",
            exposure=AssetExposure(public_ip="1.2.3.4", exposure_level="public", evidence=[_ev()]),  # ✓
            vulnerability=AssetVulnerability(risk_score=70, evidence=[_ev()]),  # ✓
            threat=AssetThreat(highest_alert_level="critical", evidence=[_ev()]),  # ✓
        )
        ahs = compute_ahs(p)
        assert ahs.state == "valid"
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)
        # overall state = partial（3/8 覆盖），但 ahs_state = valid
        assert resp["state"] == "partial"
        assert resp["ahs_state"] == "valid"
        assert resp["coverage"]["covered"] == 3
        assert resp["overall_score"] == round(3/8 * 100)  # 38

    def test_partial_2_dims_insufficient(self):
        p = AssetProfile(
            asset_id="test",
            # 只有 2 维 AHS 评估口径的 evidence → AHS state=insufficient_data
            exposure=AssetExposure(public_ip="1.2.3.4", exposure_level="public", evidence=[_ev()]),
            vulnerability=AssetVulnerability(risk_score=70, evidence=[_ev()]),
        )
        ahs = compute_ahs(p)
        assert ahs.state == "insufficient_data"
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)
        assert resp["state"] == "insufficient_data"
        assert resp["coverage"]["covered"] == 2
        assert resp["ahs_state"] == "insufficient_data"

    def test_partial_5_dims_partial_state(self):
        p = AssetProfile(
            asset_id="test",
            # 5 维全部 AHS 评估口径（3 足够，5 仍 valid）+ 部分其他维
            identity=AssetIdentity(source_id="W", identity_confidence=0.9, evidence=[_ev()]),
            ownership=AssetOwnership(owner="y", evidence=[_ev()]),
            exposure=AssetExposure(public_ip="1.2.3.4", exposure_level="public", evidence=[_ev()]),
            vulnerability=AssetVulnerability(risk_score=70, evidence=[_ev()]),
            threat=AssetThreat(highest_alert_level="critical", evidence=[_ev()]),
        )
        ahs = compute_ahs(p)
        assert ahs.state == "valid"
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)
        assert resp["state"] == "partial"  # 5/8 = partial
        assert resp["coverage"]["covered"] == 5
        assert resp["overall_score"] == int(5/8 * 100)


# ---------------------------------------------------------------------------
# 八维明细
# ---------------------------------------------------------------------------

class TestDimensionsBreakdown:
    def test_dimension_with_evidence(self):
        p = _profile_partial({"identity"})
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)

        dim = resp["dimensions"]["identity"]
        assert dim["covered"] is True
        assert dim["evidence_count"] == 1
        assert dim["confidence"] == pytest.approx(0.8, abs=0.01)

    def test_dimension_without_evidence(self):
        p = _profile_partial({"identity"})
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)

        dim = resp["dimensions"]["ownership"]
        assert dim["covered"] is False
        assert dim["evidence_count"] == 0
        assert dim["confidence"] == 0.0

    def test_all_8_dimensions_present(self):
        p = _profile_full()
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)
        assert set(resp["dimensions"].keys()) == {
            "identity", "ownership", "technology", "exposure",
            "vulnerability", "threat", "compliance", "behavior",
        }


# ---------------------------------------------------------------------------
# evidence_summary 透传
# ---------------------------------------------------------------------------

class TestEvidenceSummary:
    def test_summary_present(self):
        p = _profile_full()
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)
        es = resp["evidence_summary"]
        assert es["total_evidence"] >= 1
        assert isinstance(es["sources"], list)
        assert isinstance(es["avg_confidence"], float)
        assert es["timespan_hours"] is not None

    def test_summary_empty_when_chain_none(self):
        p = _profile_full()
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain=None)
        assert resp["evidence_summary"]["total_evidence"] == 0
        assert resp["evidence_summary"]["sources"] == []

    def test_summary_empty_when_no_evidence(self):
        p = _profile_empty()
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)
        assert resp["evidence_summary"]["total_evidence"] == 0


# ---------------------------------------------------------------------------
# AHS / profile_confidence 透传
# ---------------------------------------------------------------------------

class TestAHSPassthrough:
    def test_ahs_score_present(self):
        p = _profile_full()
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)
        assert resp["ahs_score"] == ahs.score
        assert resp["ahs_state"] == ahs.state

    def test_ahs_score_default_when_ahs_none(self):
        p = _profile_full()
        chain = build_evidence_chain(p)
        resp = _assemble_response(p, ahs_result=None, chain=chain)
        assert resp["ahs_score"] == 0  # profile.ahs_score default
        assert resp["ahs_state"] == "ahs_not_computed"

    def test_profile_confidence_present(self):
        p = _profile_full()
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)
        assert 0.0 <= resp["profile_confidence"] <= 1.0


# ---------------------------------------------------------------------------
# 响应 JSON-safe
# ---------------------------------------------------------------------------

class TestJSONSafe:
    def test_all_fields_json_serializable(self):
        """datetime / EvidenceItem 都不应直接暴露"""
        import json
        p = _profile_full()
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)
        # 应该可序列化（datetime 都已 isoformat 化）
        json.dumps(resp)  # 不抛错

    def test_computed_at_present(self):
        p = _profile_full()
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)
        assert "computed_at" in resp
        # ISO format
        datetime.fromisoformat(resp["computed_at"])


# ---------------------------------------------------------------------------
# overall_score 计算
# ---------------------------------------------------------------------------

class TestOverallScore:
    def test_overall_score_formula(self):
        """overall_score = coverage_ratio × 100，四舍五入到整数"""
        p = _profile_partial({"identity", "ownership", "exposure", "vulnerability", "threat"})  # 5/8
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)
        assert resp["overall_score"] == 62  # 5/8 × 100 = 62.5 → 62

    def test_overall_score_8_of_8(self):
        p = _profile_full()
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)
        assert resp["overall_score"] == 100

    def test_overall_score_0_of_8(self):
        p = _profile_empty()
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)
        assert resp["overall_score"] == 0


# ---------------------------------------------------------------------------
# 集成测试：与 AHS 联动
# ---------------------------------------------------------------------------

class TestIntegrationAHS:
    def test_high_risk_low_ahs(self):
        """高风险画像 → AHS 低 + 完整度仍 100%（完整≠健康）"""
        p = AssetProfile(
            asset_id="high-risk",
            identity=AssetIdentity(source_id="W", evidence=[_ev()]),
            ownership=AssetOwnership(owner="x", business_impact="core", data_sensitivity="extreme",
                                     protection_level="level_5", evidence=[_ev()]),
            technology=AssetTechnology(os_name="Linux", evidence=[_ev()]),
            exposure=AssetExposure(public_ip="1.2.3.4", exposure_level="public", evidence=[_ev()]),
            vulnerability=AssetVulnerability(risk_score=85, evidence=[_ev()]),
            threat=AssetThreat(highest_alert_level="critical", evidence=[_ev()]),
            compliance=AssetCompliance(compliance_fail_count=10, evidence=[_ev()]),
            behavior=AssetBehavior(profile_date="2026-10-03", evidence=[_ev()]),
        )
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)

        assert resp["overall_score"] == 100  # 完整度高
        assert resp["ahs_score"] < 50  # 但健康分低
        assert resp["state"] == "valid"

    def test_healthy_asset(self):
        p = AssetProfile(
            asset_id="healthy",
            identity=AssetIdentity(source_id="W", evidence=[_ev()]),
            ownership=AssetOwnership(owner="x", business_impact="ignorable", data_sensitivity="negligible",
                                     protection_level="level_1", evidence=[_ev()]),
            technology=AssetTechnology(os_name="Linux", evidence=[_ev()]),
            exposure=AssetExposure(exposure_level="isolated", evidence=[_ev()]),
            vulnerability=AssetVulnerability(risk_score=10, evidence=[_ev()]),
            threat=AssetThreat(evidence=[_ev()]),
            compliance=AssetCompliance(compliance_pass_count=10, evidence=[_ev()]),
            behavior=AssetBehavior(profile_date="2026-10-03", evidence=[_ev()]),
        )
        ahs = compute_ahs(p)
        p_with_ahs = apply_ahs_to_profile(p, ahs)
        chain = build_evidence_chain(p_with_ahs)
        resp = _assemble_response(p_with_ahs, ahs, chain)

        assert resp["ahs_score"] > 60  # 健康