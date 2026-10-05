"""OH-2.1 T5 — ⑦ 合规维 + ⑧ 行为维 loader 单测。"""
from __future__ import annotations

from app.services.asset_profile import AssetCompliance, AssetBehavior
from app.services.asset_profile.loaders.compliance_behavior import (
    load_compliance, load_behavior,
)


class TestLoadCompliance:
    """T5 — ⑦ 合规维 loader 单测（3 例）。"""

    def test_full_seeded_returns_findings(self, db_session, sample_asset_for_profile):
        """完整 seed（1 fail finding）→ fail_count=1。"""
        result = load_compliance(db_session, sample_asset_for_profile)
        assert isinstance(result, AssetCompliance)
        assert result.data_classification == "confidential"
        assert result.compliance_fail_count == 1
        assert result.compliance_pass_count == 0
        assert result.compliance_unknown_count == 0
        assert result.last_compliance_run_at is not None

    def test_minimal_asset_no_findings(self, db_session, minimal_asset):
        """最小 asset → 全 0, last_run=None。"""
        result = load_compliance(db_session, minimal_asset)
        assert isinstance(result, AssetCompliance)
        assert result.compliance_fail_count == 0
        assert result.compliance_pass_count == 0
        assert result.compliance_unknown_count == 0
        assert result.last_compliance_run_at is None

    def test_evidence_attached(self, db_session, sample_asset_for_profile):
        """evidence.source = soc_compliance_findings。"""
        result = load_compliance(db_session, sample_asset_for_profile)
        assert len(result.evidence) >= 1
        assert result.evidence[0].source == "soc_compliance_findings"


class TestLoadBehavior:
    """T5 — ⑧ 行为维 loader 单测（3 例）。"""

    def test_full_seeded_returns_profile(self, db_session, sample_asset_for_profile):
        """完整 seed（BehaviorProfile 1 行）→ tags 去 name 列表。"""
        result = load_behavior(db_session, sample_asset_for_profile)
        assert isinstance(result, AssetBehavior)
        assert result.traffic_type == "human"
        assert result.status == "ok"
        assert result.total_visits == 500
        assert result.tags == ["研究型"]  # tags=[{"name": "研究型"}] → ["研究型"]
        assert result.profile_date is not None
        assert isinstance(result.layer_visit, dict)
        assert result.layer_visit.get("ACT") == 0.6

    def test_minimal_asset_no_profile(self, db_session, minimal_asset):
        """最小 asset（无 BehaviorProfile）→ 全空 profile_date=None, total=0。"""
        result = load_behavior(db_session, minimal_asset)
        assert isinstance(result, AssetBehavior)
        assert result.profile_date is None
        assert result.total_visits == 0
        assert result.tags == []
        assert result.top_domain_count == 0
        # 仍有 evidence（标注数据源不可用）

    def test_evidence_attached(self, db_session, sample_asset_for_profile):
        """evidence.source = soc_behavior_profiles。"""
        result = load_behavior(db_session, sample_asset_for_profile)
        assert len(result.evidence) >= 1
        assert result.evidence[0].source == "soc_behavior_profiles"

class TestComplianceS4Rating:
    """OH-2.7 — ⑦ 合规维 S4 等保定级接入。"""

    def test_no_system_defaults(self, db_session, minimal_asset):
        result = load_compliance(db_session, minimal_asset)
        assert result.rated_system_count == 0
        assert result.system_rating_status is None
        # 资产默认等级 level_2/manual（模型 default）
        assert result.protection_level == "level_2"
        assert result.protection_level_source == "manual"

    def test_system_rating_weakest_wins(self, db_session, minimal_asset):
        from app.models.business_system import (
            AssetBusiness, BusinessSystem,
        )
        s1 = BusinessSystem(code="c1", name="confirmed-sys",
                            business_impact="medium", data_sensitivity="medium",
                            rating_status="confirmed", protection_level="level_3")
        s2 = BusinessSystem(code="c2", name="unrated-sys",
                            business_impact="medium", data_sensitivity="medium")
        db_session.add_all([s1, s2])
        db_session.flush()
        db_session.add_all([
            AssetBusiness(asset_id=minimal_asset.id, system_id=s1.id, role="app"),
            AssetBusiness(asset_id=minimal_asset.id, system_id=s2.id, role="db"),
        ])
        db_session.commit()

        result = load_compliance(db_session, minimal_asset)
        assert result.rated_system_count == 2
        assert result.system_rating_status == "unrated"  # 最落后者
        # 有系统关联 → evidence 含 soc_business_systems
        sources = {e.source for e in result.evidence}
        assert "soc_business_systems" in sources
