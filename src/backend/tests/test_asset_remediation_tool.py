"""OH-5.6 修复助手单测（mock call_api）。"""
from __future__ import annotations

import pytest

from app.mcp.tools import asset_base
from app.mcp.tools.asset_base import ToolValidationError
from app.mcp.tools.asset_remediation import (
    RemediationAdvanceTool,
    RemediationAssignTool,
    RemediationCreateTool,
    RemediationDetailTool,
    RemediationListTool,
)


def _patch(monkeypatch, payload, captured=None):
    def _api(m, p, params=None, json_body=None):
        if captured is not None:
            captured.update(method=m, path=p, params=params, body=json_body)
        return payload

    monkeypatch.setattr(asset_base, "call_api", _api)


class TestList:
    def test_filters_passthrough_and_evidence(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {"total": 3, "open_count": 2, "items": []}, captured)
        r = RemediationListTool().run(status="open", source_type="compliance")
        assert captured["params"] == {"status": "open", "source_type": "compliance"}
        assert r.evidence[0]["open_count"] == 2

    def test_illegal_status(self):
        with pytest.raises(ToolValidationError):
            RemediationListTool().run(status="done")


class TestDetail:
    def test_chain_and_source_evidence(self, monkeypatch):
        _patch(monkeypatch, {
            "id": "t1", "status": "in_progress",
            "created_by": "admin", "assignee": "ops",
            "resolved_by": None, "verified_by": None,
            "source_type": "reconciliation",
            "detail": {"reconciliation_type": "shadow"},
        })
        r = RemediationDetailTool().run(ticket_id="t1")
        kinds = {e["type"] for e in r.evidence}
        assert kinds == {"responsibility_chain", "source_snapshot"}


class TestCreate:
    def test_request_body(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {"id": "t9", "status": "open", "occurrence_count": 1}, captured)
        r = RemediationCreateTool().run(
            source_type="compliance", source_id="f1", assignee="ops",
        )
        assert captured["method"] == "POST"
        assert captured["path"] == "/assets/remediation/tickets"
        assert captured["body"] == {
            "source_type": "compliance", "source_id": "f1", "assignee": "ops",
        }
        assert r.evidence[0]["id"] == "t9"

    def test_source_type_enum(self):
        with pytest.raises(ToolValidationError):
            RemediationCreateTool().run(source_type="manual", source_id="x")

    def test_missing_source_id(self):
        with pytest.raises(ToolValidationError):
            RemediationCreateTool().run(source_type="compliance")


class TestAssign:
    def test_request_shape(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {"assignee": "ops", "due_at": None}, captured)
        RemediationAssignTool().run(ticket_id="t1", assignee="ops")
        assert captured["path"] == "/assets/remediation/tickets/t1/assign"
        assert captured["body"] == {"assignee": "ops"}

    def test_assignee_required(self):
        with pytest.raises(ToolValidationError):
            RemediationAssignTool().run(ticket_id="t1")


class TestAdvance:
    def test_advance_body(self, monkeypatch):
        captured = {}
        _patch(monkeypatch, {"status": "resolved", "resolved_by": "ops"}, captured)
        r = RemediationAdvanceTool().run(
            ticket_id="t1", to_status="resolved", note="已补录台账",
        )
        assert captured["path"] == "/assets/remediation/tickets/t1/advance"
        assert captured["body"] == {"to_status": "resolved", "note": "已补录台账"}
        assert r.evidence[0]["status"] == "resolved"

    @pytest.mark.parametrize("bad", ["open", "done", ""])
    def test_illegal_to_status(self, bad):
        with pytest.raises(ToolValidationError):
            RemediationAdvanceTool().run(ticket_id="t1", to_status=bad)
