"""OH-2.5 画像覆盖率看板聚合单测。

覆盖：
- _bucket_label 分桶边界
- _aggregate_responses 纯函数：
  - 全量 computed / 含 error / 空输入
  - 均值（overall_score / profile_confidence / ahs_score）
  - state_distribution
  - dimension_coverage（covered/missing/ratio/avg_confidence）
  - score_distribution 直方图
  - worst_assets 排序 + missing_dims
  - JSON 安全
"""
from __future__ import annotations

import json

import pytest

from app.api.asset_completeness import (
    _AGG_DIMENSIONS,
    _bucket_label,
    _aggregate_responses,
)


# ---------------------------------------------------------------------------
# 构造器
# ---------------------------------------------------------------------------

_DIMS_ALL_COVERED = {
    d: {"covered": True, "evidence_count": 2, "confidence": 0.9} for d in _AGG_DIMENSIONS
}


def _resp(
    asset_id: str = "a-1",
    overall_score: int = 75,
    state: str = "partial",
    ahs_score: float = 80.0,
    profile_confidence: float = 0.75,
    dimensions: dict | None = None,
) -> dict:
    return {
        "asset_id": asset_id,
        "overall_score": overall_score,
        "state": state,
        "ahs_score": ahs_score,
        "ahs_state": "valid",
        "profile_confidence": profile_confidence,
        "dimensions": dimensions if dimensions is not None else _DIMS_ALL_COVERED,
        "coverage": {"total": 8, "covered": 8, "missing": 0, "ratio": 1.0},
        "evidence_summary": {},
        "evidence_timeline": [],
        "computed_at": "2026-10-03T00:00:00+00:00",
    }


def _entry(asset_id: str, resp: dict, name: str | None = None, ip: str | None = None) -> dict:
    return {
        "asset_id": asset_id,
        "asset_name": name or f"asset-{asset_id}",
        "asset_ip": ip or "192.168.1.1",
        "asset_type": "server",
        "response": resp,
    }


# ---------------------------------------------------------------------------
# _bucket_label
# ---------------------------------------------------------------------------

class TestBucketLabel:
    def test_boundaries(self):
        assert _bucket_label(0) == "0-20"
        assert _bucket_label(20) == "0-20"
        assert _bucket_label(21) == "21-40"
        assert _bucket_label(60) == "41-60"
        assert _bucket_label(61) == "61-80"
        assert _bucket_label(100) == "81-100"

    def test_out_of_range_clamps(self):
        assert _bucket_label(-5) == "0-20"
        assert _bucket_label(150) == "81-100"


# ---------------------------------------------------------------------------
# 基本聚合
# ---------------------------------------------------------------------------

class TestAggregateBasic:
    def test_full_computed(self):
        entries = [
            _entry("a", _resp(overall_score=80, ahs_score=70, profile_confidence=0.8)),
            _entry("b", _resp(overall_score=60, ahs_score=90, profile_confidence=0.6)),
        ]
        agg = _aggregate_responses(entries)
        assert agg["total_assets"] == 2
        assert agg["computed_assets"] == 2
        assert agg["error_assets"] == 0
        cov = agg["aggregate_coverage"]
        assert cov["avg_overall_score"] == 70.0
        assert cov["avg_ahs_score"] == 80.0
        assert cov["avg_profile_confidence"] == 0.7

    def test_errors_excluded_from_avg(self):
        entries = [
            _entry("a", _resp(overall_score=80)),
            _entry("bad", {"state": "error", "error": "boom"}),
        ]
        agg = _aggregate_responses(entries)
        assert agg["total_assets"] == 2
        assert agg["computed_assets"] == 1
        assert agg["error_assets"] == 1
        assert agg["aggregate_coverage"]["avg_overall_score"] == 80.0

    def test_empty_input(self):
        agg = _aggregate_responses([])
        assert agg["total_assets"] == 0
        assert agg["computed_assets"] == 0
        assert agg["aggregate_coverage"]["avg_overall_score"] == 0.0
        assert all(d["ratio"] == 0.0 for d in agg["dimension_coverage"])
        assert all(v == 0 for v in agg["score_distribution"].values())
        assert agg["worst_assets"] == []


class TestStateDistribution:
    def test_counts_by_state(self):
        entries = [
            _entry("a", _resp(state="valid")),
            _entry("b", _resp(state="valid")),
            _entry("c", _resp(state="partial")),
            _entry("d", _resp(state="insufficient_data")),
            _entry("e", {"state": "error"}),
        ]
        agg = _aggregate_responses(entries)
        sd = agg["aggregate_coverage"]["state_distribution"]
        assert sd == {"valid": 2, "partial": 1, "insufficient_data": 1, "error": 1}


# ---------------------------------------------------------------------------
# dimension_coverage
# ---------------------------------------------------------------------------

class TestDimensionCoverage:
    def test_partial_dims(self):
        dims_a = {d: {"covered": True, "evidence_count": 1, "confidence": 0.8} for d in _AGG_DIMENSIONS}
        dims_b = {d: {"covered": False, "evidence_count": 0, "confidence": 0.0} for d in _AGG_DIMENSIONS}
        # b 只覆盖 identity（低置信度）
        dims_b["identity"] = {"covered": True, "evidence_count": 1, "confidence": 0.4}
        entries = [
            _entry("a", _resp(dimensions=dims_a)),
            _entry("b", _resp(dimensions=dims_b)),
        ]
        agg = _aggregate_responses(entries)
        by_dim = {d["dimension"]: d for d in agg["dimension_coverage"]}
        assert len(by_dim) == 8
        assert by_dim["identity"]["covered"] == 2
        assert by_dim["identity"]["missing"] == 0
        assert by_dim["identity"]["ratio"] == 1.0
        assert by_dim["identity"]["avg_confidence"] == 0.6  # (0.8+0.4)/2
        assert by_dim["ownership"]["covered"] == 1
        assert by_dim["ownership"]["missing"] == 1
        assert by_dim["ownership"]["ratio"] == 0.5
        assert by_dim["ownership"]["avg_confidence"] == 0.8

    def test_order_matches_dimensions(self):
        agg = _aggregate_responses([_entry("a", _resp())])
        dims = [d["dimension"] for d in agg["dimension_coverage"]]
        assert dims == list(_AGG_DIMENSIONS)


# ---------------------------------------------------------------------------
# score_distribution
# ---------------------------------------------------------------------------

class TestScoreDistribution:
    def test_histogram(self):
        entries = [
            _entry("a", _resp(overall_score=10)),
            _entry("b", _resp(overall_score=35)),
            _entry("c", _resp(overall_score=50)),
            _entry("d", _resp(overall_score=75)),
            _entry("e", _resp(overall_score=95)),
        ]
        agg = _aggregate_responses(entries)
        sd = agg["score_distribution"]
        assert sd == {"0-20": 1, "21-40": 1, "41-60": 1, "61-80": 1, "81-100": 1}

    def test_error_not_counted(self):
        entries = [
            _entry("a", _resp(overall_score=10)),
            _entry("bad", {"state": "error"}),
        ]
        agg = _aggregate_responses(entries)
        assert agg["score_distribution"]["0-20"] == 1
        assert sum(agg["score_distribution"].values()) == 1


# ---------------------------------------------------------------------------
# worst_assets
# ---------------------------------------------------------------------------

class TestWorstAssets:
    def test_sorted_ascending_top5(self):
        entries = [
            _entry(f"a{i}", _resp(asset_id=f"a{i}", overall_score=s))
            for i, s in enumerate([90, 10, 50, 30, 70, 20, 60])
        ]
        agg = _aggregate_responses(entries)
        worst = agg["worst_assets"]
        assert len(worst) == 5
        assert [w["overall_score"] for w in worst] == [10, 20, 30, 50, 60]

    def test_missing_dims_listed(self):
        dims = {d: {"covered": True, "evidence_count": 1, "confidence": 0.9} for d in _AGG_DIMENSIONS}
        dims["threat"] = {"covered": False, "evidence_count": 0, "confidence": 0.0}
        dims["behavior"] = {"covered": False, "evidence_count": 0, "confidence": 0.0}
        entries = [_entry("a", _resp(dimensions=dims))]
        agg = _aggregate_responses(entries)
        assert agg["worst_assets"][0]["missing_dims"] == ["threat", "behavior"]

    def test_carries_asset_meta(self):
        entries = [_entry("xyz", _resp(), name="db-server", ip="10.0.0.5")]
        agg = _aggregate_responses(entries)
        w = agg["worst_assets"][0]
        assert w["asset_id"] == "xyz"
        assert w["asset_name"] == "db-server"
        assert w["asset_ip"] == "10.0.0.5"
        assert w["asset_type"] == "server"


# ---------------------------------------------------------------------------
# JSON 安全
# ---------------------------------------------------------------------------

class TestJSONSafe:
    def test_fully_serializable(self):
        entries = [
            _entry("a", _resp()),
            _entry("bad", {"state": "error", "error": "boom"}),
        ]
        agg = _aggregate_responses(entries)
        agg["computed_at"] = "2026-10-03T00:00:00+00:00"
        agg["truncated"] = False
        # 不抛异常即通过
        json.dumps(agg, ensure_ascii=False)
