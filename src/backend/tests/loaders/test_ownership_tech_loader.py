"""OH-2.1 T3 — ② 归属维 + ③ 技术维 loader 单测。"""
from __future__ import annotations

from app.services.asset_profile import AssetOwnership, AssetTechnology
from app.services.asset_profile.loaders.ownership_tech import (
    load_ownership, load_technology,
)


class TestLoadOwnership:
    """T3 — ② 归属维 loader 单测（3 例）。"""

    def test_full_seeded_returns_business_systems(self, db_session, sample_asset_for_profile):
        """完整 seed → 关联 BusinessSystem 列表填入。"""
        result = load_ownership(db_session, sample_asset_for_profile)
        assert isinstance(result, AssetOwnership)
        assert "SOC 平台" in result.business_systems
        assert "soc-platform" in result.business_system_codes
        assert result.owner == "张三"
        assert result.business_impact == "core"
        assert result.data_sensitivity == "high"
        assert result.protection_level == "level_4"

    def test_minimal_asset_empty(self, db_session, minimal_asset):
        """最小 asset → 全空（无 business_systems）。"""
        result = load_ownership(db_session, minimal_asset)
        assert isinstance(result, AssetOwnership)
        assert result.owner is None
        assert result.business_systems == []
        assert result.business_system_codes == []

    def test_evidence_attached(self, db_session, sample_asset_for_profile):
        """evidence 非空且 source = soc_assets。"""
        result = load_ownership(db_session, sample_asset_for_profile)
        assert len(result.evidence) >= 1
        assert result.evidence[0].source == "soc_assets"


class TestLoadTechnology:
    """T3 — ③ 技术维 loader 单测（4 例）。"""

    def test_full_seeded_returns_ports_and_services(self, db_session, sample_asset_for_profile):
        """完整 seed（3 端口：22 ssh + 80 nginx + 443 nginx）→ services 去重。"""
        result = load_technology(db_session, sample_asset_for_profile)
        assert isinstance(result, AssetTechnology)
        assert result.os_name == "Ubuntu 22.04"
        assert result.os_version == "5.15"
        assert result.open_ports_count == 3
        # services 去重：["nginx", "ssh"] 排序后
        assert result.services == ["nginx", "ssh"]

    def test_minimal_asset_empty(self, db_session, minimal_asset):
        """最小 asset → open_ports=0, services=[], components=[]。"""
        result = load_technology(db_session, minimal_asset)
        assert isinstance(result, AssetTechnology)
        assert result.open_ports_count == 0
        assert result.services == []
        assert result.components == []

    def test_hardware_info_preserved(self, db_session, sample_asset_for_profile):
        """hardware_info 是 dict 直接复制（JSONB 字段）。"""
        result = load_technology(db_session, sample_asset_for_profile)
        assert isinstance(result.hardware_info, dict)
        assert result.hardware_info.get("cpu") == "Intel Xeon"

    def test_evidence_attached(self, db_session, sample_asset_for_profile):
        """evidence.source = soc_assets。"""
        result = load_technology(db_session, sample_asset_for_profile)
        assert len(result.evidence) >= 1
        assert result.evidence[0].source == "soc_assets"