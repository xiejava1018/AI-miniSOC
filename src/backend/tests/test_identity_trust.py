"""OH-3.2 单资产身份可信度评分单测。

覆盖：三维度（coverage/corroboration/strength）构成、
核心安全语义（单源弱信号不可 trusted）、强锚提分、多源佐证、
来源去重、三档阈值、to_dict、边界与异常。
"""
from __future__ import annotations

import pytest

from app.services import identity_fusion as fusion
from app.services.identity_fusion import (
    FusionError,
    score_identity_trust,
)


# ----------------------------------------------------------------- 核心安全语义


class TestCoreSafetySemantics:
    def test_single_source_weak_signals_not_trusted(self):
        # 只有 IP + 主机名（弱信号），单源
        r = score_identity_trust({"asset_ip": "10.0.0.1", "name": "host"})
        assert r.tier == "unverified"
        assert r.eligible_for_reasoning is False
        assert r.source_count == 1
        assert r.strong_anchors == []

    def test_weak_signals_multiple_sources_still_low(self):
        # 弱信号即使双源，缺强锚且覆盖低 → 仍不 trusted
        r = score_identity_trust(
            {"asset_ip": "10.0.0.1", "name": "host"},
            sources=[{"source": "wazuh"}, {"source": "nmap"}],
        )
        assert r.tier == "unverified"
        assert r.eligible_for_reasoning is False

    def test_full_identity_multi_source_trusted(self):
        asset = {
            "asset_ip": "10.0.0.1",
            "name": "h",
            "mac_address": "00:11:22:33:44:55",
            "wazuh_agent_id": "001",
            "hardware_info": {"serial_number": "SN1"},
        }
        r = score_identity_trust(
            asset,
            sources=[{"source": "wazuh"}, {"source": "nmap"}, {"source": "manual"}],
        )
        assert r.tier == "trusted"
        assert r.eligible_for_reasoning is True
        assert r.identity_confidence == pytest.approx(1.0)


# ----------------------------------------------------------------- 维度构成


class TestDimensionComposition:
    def test_coverage_weighted(self):
        # 仅 wazuh_agent（覆盖权重 .30）
        r = score_identity_trust({"wazuh_agent_id": "001"})
        assert r.coverage_score == pytest.approx(0.30)
        assert "wazuh_agent" in r.factors_present

    def test_strength_strong_anchor(self):
        r = score_identity_trust({"wazuh_agent_id": "001"})
        assert r.strength_score == pytest.approx(0.6)
        assert r.strong_anchors == ["wazuh_agent"]

    def test_strength_multiple_anchors_increase(self):
        asset = {"wazuh_agent_id": "001", "mac_address": "00:11:22:33:44:55"}
        r = score_identity_trust(asset)
        assert r.strength_score == pytest.approx(0.8)
        assert set(r.strong_anchors) == {"wazuh_agent", "mac"}

    def test_corroboration_default_single_source(self):
        r = score_identity_trust({"asset_ip": "10.0.0.1"})
        assert r.source_count == 1
        assert r.corroboration_score == pytest.approx(0.45)

    def test_corroboration_three_plus_sources_caps(self):
        r = score_identity_trust(
            {"asset_ip": "10.0.0.1"},
            sources=[{"source": "a"}, {"source": "b"}, {"source": "c"}, {"source": "d"}],
        )
        assert r.source_count == 4
        assert r.corroboration_score == pytest.approx(1.0)


# ----------------------------------------------------------------- 来源去重


class TestSourceDedup:
    def test_duplicate_source_not_inflated(self):
        # 同一来源多条记录应去重
        r = score_identity_trust(
            {"asset_ip": "10.0.0.1"},
            sources=[{"source": "wazuh"}, {"source": "wazuh"}, {"source": "wazuh"}],
        )
        assert r.source_count == 1
        assert r.corroboration_score == pytest.approx(0.45)

    def test_sources_as_objects(self):
        class S:
            def __init__(self, name):
                self.source = name

        r = score_identity_trust(
            {"asset_ip": "10.0.0.1"},
            sources=[S("wazuh"), S("nmap")],
        )
        assert r.source_count == 2
        assert r.corroboration_score == pytest.approx(0.8)

    def test_empty_sources_list_zero(self):
        r = score_identity_trust({"asset_ip": "10.0.0.1"}, sources=[])
        assert r.source_count == 0
        assert r.corroboration_score == 0.0


# ----------------------------------------------------------------- 分档


class TestTiers:
    def test_tentative_band(self):
        # 单源 + 强锚（agent + MAC）落 tentative
        asset = {"wazuh_agent_id": "001", "mac_address": "00:11:22:33:44:55"}
        r = score_identity_trust(asset)
        assert r.tier == "tentative"
        # 可入图谱但不可自动推理
        assert r.eligible_for_reasoning is False

    def test_custom_thresholds(self):
        asset = {"wazuh_agent_id": "001", "mac_address": "00:11:22:33:44:55"}
        r = score_identity_trust(asset, trusted_threshold=0.55, tentative_threshold=0.3)
        assert r.tier == "trusted"
        assert r.eligible_for_reasoning is True


# ----------------------------------------------------------------- 结构与异常


class TestStructureAndErrors:
    def test_to_dict_keys(self):
        d = score_identity_trust({"asset_ip": "10.0.0.1"}).to_dict()
        expected = {
            "identity_confidence", "tier", "coverage_score", "corroboration_score",
            "strength_score", "factors_present", "strong_anchors", "source_count",
            "eligible_for_reasoning", "trusted_threshold", "tentative_threshold",
        }
        assert set(d.keys()) == expected

    def test_none_asset_raises(self):
        with pytest.raises(FusionError):
            score_identity_trust(None)

    def test_invalid_threshold_order_raises(self):
        with pytest.raises(FusionError):
            score_identity_trust(
                {"asset_ip": "10.0.0.1"},
                trusted_threshold=0.3,
                tentative_threshold=0.8,
            )

    def test_empty_asset_unverified(self):
        r = score_identity_trust({})
        assert r.tier == "unverified"
        # 空身份因子：coverage=0/strength=0，但默认单源 corroboration=.45 → .1575
        assert r.identity_confidence == pytest.approx(0.1575)
        assert r.factors_present == []
