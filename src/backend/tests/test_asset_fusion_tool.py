"""OH-5.3 融合助手单测（mock call_api，无后端往返）。

覆盖三个工具：
  - list：默认 pending 参数、evidence pending_count
  - detail：路径含 review_id；evidence 有 fusion_score + candidates；confidence 用真实 best_score
  - resolve：POST resolve 路径与 decision body；非法 decision 被 enum 拦截；evidence resolved
"""
from __future__ import annotations

import pytest

from app.mcp.tools import asset_base
from app.mcp.tools.asset_base import ToolValidationError
from app.mcp.tools.asset_fusion import (
    FusionDetailTool,
    FusionPendingTool,
    FusionResolveTool,
)


def _patch(monkeypatch, payload):
    monkeypatch.setattr(
        asset_base, "call_api",
        lambda m, p, params=None, json_body=None: payload,
    )


class TestPending:
    def test_default_status_pending(self, monkeypatch):
        captured = {}

        def _api(m, p, params=None, json_body=None):
            captured.update(method=m, path=p, params=params)
            return {"total": 2, "pending_count": 2, "items": []}

        monkeypatch.setattr(asset_base, "call_api", _api)
        t = FusionPendingTool()
        result = t.run()

        assert captured["method"] == "GET"
        assert captured["path"] == "/assets/attribution/reviews"
        assert captured["params"]["status"] == "pending"
        assert result.evidence[0]["pending_count"] == 2

    def test_illegal_status_enum(self):
        with pytest.raises(ToolValidationError):
            FusionPendingTool().run(status="bogus")


class TestDetail:
    def test_detail_evidence_and_real_confidence(self, monkeypatch):
        _patch(monkeypatch, {
            "id": "r1",
            "best_score": {"confidence": 0.667, "decision": "needs_review"},
            "candidates": [
                {"asset_id": "a1", "asset_ip": "10.0.0.1", "name": "h1",
                 "score": {"confidence": 0.667, "decision": "needs_review"}},
                {"asset_id": "a2", "asset_ip": "10.0.0.2", "name": "h2",
                 "score": {"confidence": 0.2, "decision": "distinct"}},
            ],
        })
        t = FusionDetailTool()
        result = t.run(review_id="r1")

        assert result.confidence == 0.667
        kinds = {e["type"] for e in result.evidence}
        assert kinds == {"fusion_score", "candidates"}

        cands = next(e for e in result.evidence if e["type"] == "candidates")["candidates"]
        assert cands[0]["confidence"] == 0.667
        assert cands[1]["decision"] == "distinct"

    def test_review_id_required(self):
        with pytest.raises(ToolValidationError):
            FusionDetailTool().run()


class TestResolve:
    def test_merge_request_shape(self, monkeypatch):
        captured = {}

        def _api(m, p, params=None, json_body=None):
            captured.update(method=m, path=p, body=json_body)
            return {"status": "merged", "asset_id": "a1", "resolved_by": "op",
                    "best_score": {"confidence": 0.667}}

        monkeypatch.setattr(asset_base, "call_api", _api)
        t = FusionResolveTool()
        result = t.run(review_id="r1", decision="merge", note="确认IP漂移")

        assert captured["method"] == "POST"
        assert captured["path"] == "/assets/attribution/reviews/r1/resolve"
        assert captured["body"] == {"decision": "merge", "note": "确认IP漂移"}
        assert result.confidence == 0.667
        assert result.evidence[0]["status"] == "merged"

    def test_target_asset_id_passed(self, monkeypatch):
        captured = {}

        def _api(m, p, params=None, json_body=None):
            captured["body"] = json_body
            return {"status": "merged", "asset_id": "a9"}

        monkeypatch.setattr(asset_base, "call_api", _api)
        FusionResolveTool().run(review_id="r1", decision="merge", target_asset_id="a9")
        assert captured["body"]["target_asset_id"] == "a9"

    @pytest.mark.parametrize("decision", ["", "approve", "delete"])
    def test_illegal_decision_rejected(self, decision):
        with pytest.raises(ToolValidationError):
            FusionResolveTool().run(review_id="r1", decision=decision)

    def test_missing_review_id(self):
        with pytest.raises(ToolValidationError):
            FusionResolveTool().run(decision="merge")
