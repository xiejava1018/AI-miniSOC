"""OH-5.4 稽核助手单测（mock call_api，无后端往返）。"""
from __future__ import annotations

import pytest

from app.mcp.tools import asset_base
from app.mcp.tools.asset_base import ToolValidationError
from app.mcp.tools.asset_audit import (
    CoverageAuditTool,
    DataHealthAuditTool,
    ProtectionSuggestTool,
    ReconSummaryAuditTool,
    SystemsAuditTool,
)


def _patch(monkeypatch, payload, captured=None):
    def _api(m, p, params=None, json_body=None):
        if captured is not None:
            captured.update(method=m, path=p, params=params, body=json_body)
        return payload

    monkeypatch.setattr(asset_base, "call_api", _api)


class TestSystemsAudit:
    def test_distribution_evidence(self, monkeypatch):
        _patch(monkeypatch, {
            "total": 3,
            "items": [
                {"name": "a", "rating_status": "unrated"},
                {"name": "b", "rating_status": "suggested"},
                {"name": "c", "rating_status": "suggested"},
            ],
        })
        t = SystemsAuditTool()
        result = t.run()
        dist = result.evidence[0]["distribution"]
        assert dist == {"unrated": 1, "suggested": 2}

    def test_rating_status_enum(self):
        with pytest.raises(ToolValidationError):
            SystemsAuditTool().run(rating_status="bogus")

    def test_uses_page_params(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {"total": 0, "items": []}, captured)
        SystemsAuditTool().run()
        assert captured["path"] == "/business-systems"
        assert captured["params"]["page_size"] == 100


class TestCoverage:
    def test_confidence_from_rate(self, monkeypatch):
        _patch(monkeypatch, {"coverage_rate": 61.2, "total_assets": 73,
                             "linked_assets": 45})
        t = CoverageAuditTool()
        result = t.run()
        assert result.confidence == pytest.approx(0.612, abs=1e-4)
        assert result.evidence[0]["coverage_rate"] == 61.2

    def test_no_params(self):
        assert CoverageAuditTool().schema["properties"] == {}


class TestSuggest:
    def test_post_path_and_evidence(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {
            "suggested_protection_level": "level_2",
            "suggestion_basis": {"score": 40},
        }, captured)
        t = ProtectionSuggestTool()
        result = t.run(system_id="s1")

        assert captured["method"] == "POST"
        assert captured["path"] == "/business-systems/s1/suggest-protection-level"
        ev = result.evidence[0]
        assert ev["suggested_level"] == "level_2"
        assert ev["basis"] == {"score": 40}

    def test_system_id_required(self):
        with pytest.raises(ToolValidationError):
            ProtectionSuggestTool().run()


class TestDataHealth:
    def test_summary_evidence(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {"summary": {"sources_healthy": 2}}, captured)
        t = DataHealthAuditTool()
        result = t.run()
        assert result.evidence[0]["summary"] == {"sources_healthy": 2}
        assert captured["params"]["dead_letter_limit"] == 5

    def test_dead_letter_limit(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {"summary": {}}, captured)
        DataHealthAuditTool().run(dead_letter_limit=10)
        assert captured["params"]["dead_letter_limit"] == 10


class TestReconSummary:
    def test_by_type_evidence(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {
            "has_data": True,
            "by_type": {"shadow": 2, "offline": 1},
            "pending_total": 3,
            "freshness": {"asset_updated_at": "2026-10-05"},
        }, captured)
        t = ReconSummaryAuditTool()
        result = t.run()
        assert captured["path"] == "/assets/reconcile/summary"
        assert result.evidence[0]["by_type"] == {"shadow": 2, "offline": 1}
        assert result.evidence[0]["pending_total"] == 3
