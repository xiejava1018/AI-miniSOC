"""OH-2.1 build_profile 编排器单测。"""
from __future__ import annotations

from app.services.asset_profile import (
    AssetProfile, CoverageInfo, DIMENSIONS,
    empty_profile,
)
from app.services.asset_profile.builder import (
    build_profile, build_profile_dict,
)


class TestBuildProfile:
    """build_profile 单测（5 例）。"""

    def test_full_seeded_all_dims_present(self, db_session, sample_asset_for_profile):
        """完整 seed → 8 维全填, coverage.ratio > 0.5。"""
        profile = build_profile(db_session, sample_asset_for_profile)
        assert isinstance(profile, AssetProfile)
        assert profile.asset_id == str(sample_asset_for_profile.id)
        # 8 维均非全空（至少有一个非 None 字段）
        assert profile.identity.source_id == "W-NET-001"
        assert profile.ownership.owner == "张三"
        assert profile.technology.os_name == "Ubuntu 22.04"
        assert profile.exposure.public_ip == "1.2.3.4"
        assert profile.vulnerability.risk_score == 72
        assert profile.threat.open_alerts == 1
        assert profile.compliance.data_classification == "confidential"
        assert profile.behavior.total_visits == 500

    def test_coverage_calculated(self, db_session, sample_asset_for_profile):
        """coverage 字段非空, ratio > 0（至少 1 维覆盖）。"""
        profile = build_profile(db_session, sample_asset_for_profile)
        assert profile.coverage is not None
        assert isinstance(profile.coverage, CoverageInfo)
        assert profile.coverage.total == len(DIMENSIONS) == 8
        assert profile.coverage.covered >= 5
        assert profile.coverage.ratio > 0.5

    def test_profile_confidence_in_range(self, db_session, sample_asset_for_profile):
        """profile_confidence ∈ [0, 1]。"""
        profile = build_profile(db_session, sample_asset_for_profile)
        assert 0.0 <= profile.profile_confidence <= 1.0
        # 完整 seed → confidence > 0.5
        assert profile.profile_confidence > 0.5

    def test_minimal_asset_low_coverage(self, db_session, minimal_asset):
        """最小 asset → coverage 大部分 missing, ratio < 0.5。"""
        profile = build_profile(db_session, minimal_asset)
        assert isinstance(profile, AssetProfile)
        assert profile.coverage.covered <= 4  # 极少信息
        assert profile.coverage.ratio < 0.6
        # confidence 也低（覆盖少）
        assert profile.profile_confidence < 0.5

    def test_build_profile_dict_json_safe(self, db_session, sample_asset_for_profile):
        """build_profile_dict 返回 JSON-safe dict（含 coverage + confidence）。"""
        d = build_profile_dict(db_session, sample_asset_for_profile)
        assert isinstance(d, dict)
        assert d["asset_id"] == str(sample_asset_for_profile.id)
        assert "identity" in d and "behavior" in d
        assert "coverage" in d and "ratio" in d["coverage"]
        assert "profile_confidence" in d
        # datetime 转 ISO string
        for dim_key in DIMENSIONS:
            ev = d[dim_key]["evidence"][0]
            assert isinstance(ev["observed_at"], str)