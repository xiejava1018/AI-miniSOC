"""OH-3.1 多因子身份融合评分单测。

覆盖：5 因子各自匹配/缺失、缺失重归一化、阈值三态、
强信号冲突压制、MAC/主机名归一化、阈值校验、to_dict 结构。
"""
from __future__ import annotations

import pytest

from app.services import identity_fusion as fusion
from app.services.identity_fusion import (
    FactorWeights,
    FusionError,
    score_fusion,
    should_auto_merge,
)


BASE = {
    "asset_ip": "10.0.0.1",
    "mac_address": "00:11:22:33:44:55",
    "name": "web1",
    "wazuh_agent_id": "001",
    "hardware_info": {"serial_number": "SN-1"},
}


# ----------------------------------------------------------------- 基本判定


class TestBasicDecision:
    def test_identical_observations_auto_merge(self):
        r = score_fusion(dict(BASE), dict(BASE))
        assert r.decision == "auto_merge"
        assert r.confidence == pytest.approx(1.0)
        assert should_auto_merge(r)

    def test_no_common_signal_distinct(self):
        r = score_fusion({"name": "x"}, {"asset_ip": "10.0.0.9"})
        assert r.decision == "distinct"
        assert r.confidence == 0.0
        assert r.participating_factors == []

    def test_result_to_dict_serializable(self):
        d = score_fusion(dict(BASE), dict(BASE)).to_dict()
        assert d["decision"] == "auto_merge"
        assert len(d["factors"]) == 5
        for f in d["factors"]:
            assert set(f.keys()) == {
                "name", "weight", "present", "match", "a_value", "b_value"
            }


# ----------------------------------------------------------------- 单因子


class TestSingleFactor:
    def test_only_mac_match_high_confidence(self):
        a = {"mac_address": BASE["mac_address"]}
        r = score_fusion(a, dict(a))
        # 只有 MAC 参与 → 归一化后 confidence=1
        assert r.confidence == pytest.approx(1.0)
        assert r.participating_factors == ["mac"]

    def test_only_ip_match_confidence_one(self):
        a = {"asset_ip": "10.0.0.1"}
        r = score_fusion(a, dict(a))
        assert r.confidence == pytest.approx(1.0)
        assert r.participating_factors == ["ip"]

    def test_mixed_match_and_miss_normalizes(self):
        # IP 同（参与且匹配）；MAC 双方有值但不同（参与不匹配）
        a = {"asset_ip": "10.0.0.1", "mac_address": "00:11:22:33:44:55"}
        b = {"asset_ip": "10.0.0.1", "mac_address": "66:77:88:99:aa:bb"}
        r = score_fusion(a, b)
        # 权重 ip .25 / mac .30，sum .55，匹配 .25 → .4545
        assert r.confidence == pytest.approx(0.25 / 0.55)


# ----------------------------------------------------------------- 缺失处理


class TestMissingSignals:
    def test_one_side_missing_not_participating(self):
        a = {"asset_ip": "10.0.0.1", "mac_address": "00:11:22:33:44:55"}
        b = {"asset_ip": "10.0.0.1"}  # MAC 缺失
        r = score_fusion(a, b)
        mac_factor = next(f for f in r.factors if f.name == "mac")
        assert mac_factor.present is False
        # 只有 IP 参与
        assert r.participating_factors == ["ip"]
        assert r.confidence == pytest.approx(1.0)

    def test_empty_string_treated_as_missing(self):
        a = {"asset_ip": "10.0.0.1", "name": ""}
        b = {"asset_ip": "10.0.0.1", "name": "   "}
        r = score_fusion(a, b)
        assert "hostname" not in r.participating_factors

    def test_missing_data_does_not_inflate_score(self):
        # 双方大量字段缺失，只有 IP 同 → 归一化后仍 1.0，但仅基于一个弱因子，
        # 这是"在已知信息内"的置信度，不应被误读为强证据
        a = {"asset_ip": "10.0.0.1"}
        r = score_fusion(a, dict(a))
        assert r.confidence == pytest.approx(1.0)
        assert len(r.participating_factors) == 1


# ----------------------------------------------------------------- 冲突压制


class TestConflictSuppression:
    def test_mac_conflict_blocks_auto_merge(self):
        a = {
            "asset_ip": "10.0.0.1",
            "name": "host",
            "wazuh_agent_id": "001",
            "mac_address": "00:11:22:33:44:55",
        }
        b = dict(a)
        b["mac_address"] = "aa:bb:cc:dd:ee:ff"
        r = score_fusion(a, b)
        assert r.confidence >= 0.6           # 加权较高（ip/主机名/agent 匹配）
        assert r.decision == "needs_review"  # 但冲突压制，不自动合并
        assert r.conflict is True
        assert r.conflict_factors == ["mac"]

    def test_hardware_conflict_blocks_auto_merge(self):
        a = {
            "asset_ip": "10.0.0.1",
            "name": "host",
            "hardware_info": {"serial_number": "SN-A"},
        }
        b = dict(a)
        b["hardware_info"] = {"serial_number": "SN-B"}
        r = score_fusion(a, b)
        assert r.decision == "needs_review"
        assert "hardware" in r.conflict_factors

    def test_ip_conflict_is_not_strong_conflict(self):
        # IP 不一致（DHCP 漂移常见）不属强冲突因子
        a = {"mac_address": "00:11:22:33:44:55", "asset_ip": "10.0.0.1"}
        b = {"mac_address": "00:11:22:33:44:55", "asset_ip": "10.0.0.2"}
        r = score_fusion(a, b)
        assert r.conflict is False
        # MAC 匹配 → 归一化后高置信，可自动合并（同 MAC 不同 IP 是漂移）
        assert r.decision == "auto_merge"


# ----------------------------------------------------------------- 归一化


class TestNormalization:
    def test_mac_separators_equivalent(self):
        a = {"mac_address": "00:11:22:33:44:55"}
        b = {"mac_address": "00-11-22-33-44-55"}
        c = {"mac_address": "001122334455"}
        assert score_fusion(a, b).confidence == pytest.approx(1.0)
        assert score_fusion(a, c).confidence == pytest.approx(1.0)

    def test_hostname_case_and_trailing_dot(self):
        a = {"name": "Web-Server"}
        b = {"name": "web-server."}
        assert score_fusion(a, b).confidence == pytest.approx(1.0)

    def test_hardware_dict_uses_serial(self):
        a = {"hardware_info": {"serial_number": "ABC123", "vendor": "Dell"}}
        b = {"hardware_info": {"serial_number": "ABC123", "vendor": "HP"}}
        assert score_fusion(a, b).confidence == pytest.approx(1.0)

    def test_hardware_dict_no_recognized_key(self):
        a = {"hardware_info": {"vendor": "Dell"}}
        b = {"hardware_info": {"vendor": "HP"}}
        r = score_fusion(a, b)
        assert "hardware" not in r.participating_factors

    def test_hardware_string(self):
        a = {"hardware_info": "SN-XYZ"}
        b = {"hardware_info": "SN-XYZ"}
        assert score_fusion(a, b).confidence == pytest.approx(1.0)


# ----------------------------------------------------------------- 自定义配置


class TestCustomConfig:
    def test_custom_weights(self):
        # 把 IP 权重设为唯一因子
        w = FactorWeights(ip=1.0, mac=0.0, hostname=0.0,
                          wazuh_agent=0.0, hardware=0.0)
        a = {"asset_ip": "10.0.0.1", "mac_address": "00:11:22:33:44:55"}
        b = {"asset_ip": "10.0.0.1", "mac_address": "99:88:77:66:55:44"}
        r = score_fusion(a, b, weights=w)
        # MAC 冲突但权重 0；IP 匹配权重 1
        assert r.decision == "auto_merge"

    def test_custom_thresholds_review_band(self):
        # IP+MAC 参与、IP 匹配 MAC 不匹配（冲突）
        a = {"asset_ip": "10.0.0.1", "mac_address": "00:11:22:33:44:55"}
        b = {"asset_ip": "10.0.0.1", "mac_address": "66:77:88:99:aa:bb"}
        r = score_fusion(a, b, auto_merge_threshold=0.9, review_threshold=0.2)
        assert r.decision == "needs_review"

    def test_invalid_threshold_order_raises(self):
        with pytest.raises(FusionError):
            score_fusion(dict(BASE), dict(BASE),
                         auto_merge_threshold=0.3, review_threshold=0.8)

    def test_none_observation_raises(self):
        with pytest.raises(FusionError):
            score_fusion(None, dict(BASE))
        with pytest.raises(FusionError):
            score_fusion(dict(BASE), None)


# ----------------------------------------------------------------- 对象输入


class TestObjectInput:
    def test_accepts_objects(self):
        class Obs:
            def __init__(self):
                self.asset_ip = "10.0.0.1"
                self.mac_address = "00:11:22:33:44:55"
                self.name = "web1"

        r = score_fusion(Obs(), Obs())
        assert r.decision == "auto_merge"
