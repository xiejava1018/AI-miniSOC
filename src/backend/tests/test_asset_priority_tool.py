"""OH-5.5 优先级助手单测（mock call_api）。"""
from __future__ import annotations

import pytest

from app.mcp.tools import asset_base
from app.mcp.tools.asset_base import ToolValidationError
from app.mcp.tools.asset_priority import (
    PriorityOverviewTool,
    SystemPriorityTool,
    TopVulnAssetsTool,
    VPTPlusTool,
)


def _patch(monkeypatch, payload, captured=None):
    def _api(m, p, params=None, json_body=None):
        if captured is not None:
            captured.update(method=m, path=p, params=params)
        return payload

    monkeypatch.setattr(asset_base, "call_api", _api)


class TestOverview:
    def test_evidence(self, monkeypatch):
        _patch(monkeypatch, {"distribution": {"high": 3}, "top10": []})
        r = PriorityOverviewTool().run()
        assert r.evidence[0]["distribution"] == {"high": 3}


class TestTopVuln:
    def test_default_limit_and_evidence(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, [{"asset": "a"}], captured)
        r = TopVulnAssetsTool().run()
        assert captured["path"] == "/vulnerabilities/stats/top-assets"
        assert captured["params"]["limit"] == 5
        assert r.evidence[0]["count"] == 1

    def test_limit_passed(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, [], captured)
        TopVulnAssetsTool().run(limit=10)
        assert captured["params"]["limit"] == 10


class TestSystemPriority:
    def test_ranking_by_protection_then_bia(self, monkeypatch):
        _patch(monkeypatch, [
            {"name": "a", "protection_level": "level_1", "business_impact": "critical"},
            {"name": "b", "protection_level": "level_3", "business_impact": "low"},
            {"name": "c", "business_impact": "medium"},   # 无等保
            {"name": "d"},                                 # 全无
        ])
        r = SystemPriorityTool().run(system_id="s1")

        names = [a["name"] for a in r.data["system_assets"]]
        assert names == ["b", "a", "c", "d"]
        assert r.data["system_assets"][0]["sort_basis"] == "protection_level"
        assert r.data["system_assets"][2]["sort_basis"] == "business_impact"
        assert r.data["system_assets"][3]["sort_basis"] == "none"
        # 4 台中 3 台有排序依据
        assert r.confidence == pytest.approx(0.75)
        assert "VPT+" in r.data["note"]

    def test_system_id_required(self):
        with pytest.raises(ToolValidationError):
            SystemPriorityTool().run()


class TestVPTPlus:
    def test_vpt_plus_request_and_evidence(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {
            "total_open": 2,
            "graph_method": "approximate_degree_centrality",
            "ranked": [
                {"vulnerability": {"cve_id": "CVE-1"}, "priority_score": 80},
                {"vulnerability": {"cve_id": "CVE-2"}, "priority_score": 40},
            ],
        }, captured)
        t = VPTPlusTool()
        result = t.run(system_id="s1", limit=10)
        assert captured["path"] == "/vulnerabilities/priority"
        assert captured["params"]["system_id"] == "s1"
        assert result.evidence[0]["total_open"] == 2
        assert result.confidence == 1.0
        assert result.evidence[0]["top"][0]["cve"] == "CVE-1"

    def test_vpt_plus_defaults(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {"total_open": 0, "ranked": []}, captured)
        VPTPlusTool().run()
        assert captured["params"] == {"limit": 20}
