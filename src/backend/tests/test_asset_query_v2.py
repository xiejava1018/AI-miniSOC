"""OH-5.2 asset_query_v2 单测。

覆盖：
  - schema：question 必填、未知参数拒绝
  - L2 模板结果：evidence 含 query_template + coverage，confidence=.9
  - L1 结果：evidence 含 l1_filters，confidence=.75
  - 诚实降级（unavailable / unsupported）：confidence=None，evidence 标 non_success
不连后端（monkeypatch call_api）。
"""
from __future__ import annotations

import pytest

from app.mcp.tools import asset_base, asset_query_v2
from app.mcp.tools.asset_base import ToolValidationError
from app.mcp.tools.asset_query_v2 import AssetQueryV2Tool


@pytest.fixture()
def tool():
    return AssetQueryV2Tool()


def _patch_api(monkeypatch, payload):
    monkeypatch.setattr(
        asset_base, "call_api",
        lambda m, p, params=None, json_body=None: payload,
    )


class TestSchema:
    def test_question_required(self, tool):
        assert "question" in tool.schema["required"]

    def test_unknown_param_rejected(self, tool):
        with pytest.raises(ToolValidationError):
            tool.run(question="x", bogus="y")

    def test_missing_question(self, tool):
        with pytest.raises(ToolValidationError):
            tool.run()


class TestL2Result:
    def test_template_evidence_and_confidence(self, tool, monkeypatch):
        _patch_api(monkeypatch, {
            "level": "L2",
            "intent": "template",
            "template_id": "port_open",
            "template_name": "开放端口查询",
            "templates_version": 2,
            "params": {"port": 3389},
            "coverage": {"total": 73, "counted": 73, "missing": 0},
            "assets": [{"ip": "10.0.0.1"}],
            "total": 1,
        })
        result = tool.run(question="谁开了3389？")

        assert result.confidence == 0.9
        kinds = {e["type"] for e in result.evidence}
        assert "query_template" in kinds
        assert "data_coverage" in kinds

        tpl = next(e for e in result.evidence if e["type"] == "query_template")
        assert tpl["template_id"] == "port_open"
        assert tpl["params"] == {"port": 3389}


class TestL1Result:
    def test_filter_evidence(self, tool, monkeypatch):
        _patch_api(monkeypatch, {
            "level": "L1",
            "intent": "filter",
            "params": {"asset_type": "server"},
            "assets": [],
        })
        result = tool.run(question="有哪些服务器？")
        assert result.confidence == 0.75
        assert any(e["type"] == "l1_filters" for e in result.evidence)


class TestDegradation:
    @pytest.mark.parametrize("intent", ["unavailable", "unsupported", "invalid_params", "error"])
    def test_non_success_has_no_confidence(self, tool, monkeypatch, intent):
        _patch_api(monkeypatch, {"level": "L1", "intent": intent, "message": "m"})
        result = tool.run(question="x")
        assert result.confidence is None
        assert any(e.get("intent") == intent for e in result.evidence
                   if e["type"] == "non_success")


class TestRequestShape:
    def test_body_contains_question_and_session(self, tool, monkeypatch):
        captured = {}

        def _api(m, p, params=None, json_body=None):
            captured["body"] = json_body
            return {"level": "L1", "intent": "filter", "params": {}}

        monkeypatch.setattr(asset_base, "call_api", _api)
        tool.run(question="hi", session_id="sess-1")
        assert captured["body"] == {"question": "hi", "session_id": "sess-1"}
