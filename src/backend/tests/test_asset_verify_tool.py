"""OH-5.7 验证助手单测（mock call_api）。"""
from __future__ import annotations

import pytest

from app.mcp.tools import asset_base
from app.mcp.tools.asset_base import ToolValidationError
from app.mcp.tools.asset_verify import (
    VerifyDecideTool,
    VerifyQueueTool,
    VerifyRetestTool,
)


def _patch(monkeypatch, payload, captured=None):
    def _api(m, p, params=None, json_body=None):
        if captured is not None:
            captured.update(method=m, path=p, params=params, body=json_body)
        return payload

    monkeypatch.setattr(asset_base, "call_api", _api)


class TestQueue:
    def test_quality_flags(self, monkeypatch):
        from datetime import datetime, timedelta, timezone
        overdue = (
            datetime.now(timezone.utc) - timedelta(days=2)
        ).isoformat()
        _patch(monkeypatch, {
            "total": 3,
            "items": [
                {"id": "t1", "resolve_note": "已补录", "due_at": None, "occurrence_count": 1},
                {"id": "t2", "resolve_note": "", "due_at": overdue, "occurrence_count": 1},
                {"id": "t3", "resolve_note": "ok", "due_at": None, "occurrence_count": 3},
            ],
        })
        r = VerifyQueueTool().run()

        assert r.data["awaiting_verification"] == 3
        assert r.data["flagged"] == 2  # t2、t3
        assert r.confidence == pytest.approx(1 / 3, abs=1e-4)
        items = {i["id"]: i["quality_issues"] for i in r.data["items"]}
        assert items["t1"] == []
        assert set(items["t2"]) == {"missing_note", "overdue"}
        assert items["t3"] == ["recurring"]
        assert "回单质检" in r.data["note"]

    def test_requests_resolved_status(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {"total": 0, "items": []}, captured)
        VerifyQueueTool().run(assignee="ops")
        assert captured["params"]["status"] == "resolved"
        assert captured["params"]["assignee"] == "ops"


class TestDecide:
    def test_pass_maps_to_verified(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {"status": "verified", "verified_by": "aud"}, captured)
        r = VerifyDecideTool().run(ticket_id="t1", verdict="pass", note="复测通过")
        assert captured["path"] == "/assets/remediation/tickets/t1/advance"
        assert captured["body"] == {"to_status": "verified", "note": "复测通过"}
        assert r.evidence[0]["verdict"] == "pass"

    def test_fail_maps_to_reopened(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {"status": "reopened"}, captured)
        VerifyDecideTool().run(ticket_id="t1", verdict="fail", note="端口仍开")
        assert captured["body"]["to_status"] == "reopened"

    def test_verdict_enum(self):
        with pytest.raises(ToolValidationError):
            VerifyDecideTool().run(ticket_id="t1", verdict="maybe")

    def test_missing_ticket(self):
        with pytest.raises(ToolValidationError):
            VerifyDecideTool().run(verdict="pass")


class TestVerifyRetest:
    def test_evaluate_default(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {"verdict": "pass", "task_status": "success"},
               captured)
        t = VerifyRetestTool()
        result = t.run(ticket_id="t1")
        assert captured["method"] == "GET"
        assert captured["path"].endswith("/t1/retest")
        assert result.confidence == 0.9
        assert result.evidence[0]["verdict"] == "pass"

    def test_trigger_post(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {"task_uuid": "x", "status": "pending"}, captured)
        VerifyRetestTool().run(ticket_id="t1", action="trigger", mode="internal")
        assert captured["method"] == "POST"
        assert captured["body"] == {"mode": "internal"}

    def test_required_ticket(self, monkeypatch):
        _patch(monkeypatch, {})
        with pytest.raises(ToolValidationError):
            VerifyRetestTool().run()
