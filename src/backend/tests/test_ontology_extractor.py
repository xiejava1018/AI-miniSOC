"""OH-1.7 本体驱动 LLM 抽取单测。

纯函数 parse_extraction + prompt 用秒级测试；OntologyExtractor 用 monkeypatch
mock ai_client，不真实调 LLM。
"""
from __future__ import annotations

import json

import pytest

from app.services import ontology_extractor as oe_mod
from app.services.ontology_extractor import (
    OntologyExtractor,
    build_extraction_prompt,
    parse_extraction,
)

ALLOWED = {
    "ipv4-addr", "domain-name", "mac-addr", "url", "user-account",
    "identity", "vulnerability", "location",
}


class TestParseExtraction:
    def test_valid_entities(self):
        raw = json.dumps({"entities": [
            {"type": "ipv4-addr", "value": "192.168.0.1", "raw": "192.168.0.1"},
            {"type": "domain-name", "value": "evil.com", "raw": "evil.com"},
        ]})
        out = parse_extraction(raw, ALLOWED)
        assert out["extracted"] is True
        assert out["entity_count"] == 2

    def test_drops_disallowed_type(self):
        raw = json.dumps({"entities": [
            {"type": "weird-x", "value": "x"},
            {"type": "ipv4-addr", "value": "1.1.1.1"},
        ]})
        out = parse_extraction(raw, ALLOWED)
        assert out["entity_count"] == 1
        assert len(out["dropped"]) == 1
        assert out["dropped"][0]["reason"] == "type_not_allowed"

    def test_drops_missing_name_value(self):
        raw = json.dumps({"entities": [{"type": "identity"}]})
        out = parse_extraction(raw, ALLOWED)
        assert out["entity_count"] == 0
        assert out["dropped"][0]["reason"] == "missing_name_or_value"

    def test_invalid_json(self):
        out = parse_extraction("not json at all", ALLOWED)
        assert out["extracted"] is False
        assert "JSON" in out["error"]

    def test_loose_json_with_surrounding_text(self):
        raw = '好的，结果如下：\n{"entities":[{"type":"url","value":"http://x"}]}\n以上。'
        out = parse_extraction(raw, ALLOWED)
        assert out["extracted"] is True
        assert out["entity_count"] == 1

    def test_empty_entities(self):
        out = parse_extraction('{"entities": []}', ALLOWED)
        assert out["extracted"] is True
        assert out["entity_count"] == 0


class TestPrompt:
    def test_prompt_includes_types_and_text(self):
        p = build_extraction_prompt("发现 10.0.0.1 开放 80 端口")
        assert "ipv4-addr" in p
        assert "10.0.0.1" in p
        assert "entities" in p


class TestExtractorMocked:
    def _make(self, db_session, llm_return: str):
        def fake_ai_chat(prompt, **kw):
            return llm_return
        # monkeypatch ai_client in the module-level import path
        import app.services.ai_client as ai_client_mod
        orig = ai_client_mod.ai_chat
        ai_client_mod.ai_chat = fake_ai_chat
        try:
            return OntologyExtractor(db_session).extract(
                "主机 192.168.5.5 存在 CVE-2024-1234")
        finally:
            ai_client_mod.ai_chat = orig

    def test_extract_success(self, db_session):
        llm = json.dumps({"entities": [
            {"type": "ipv4-addr", "value": "192.168.5.5"},
            {"type": "vulnerability", "name": "CVE-2024-1234"},
        ]})
        out = self._make(db_session, llm)
        assert out["extracted"] is True
        assert out["entity_count"] == 2
        assert out["confidence"] is not None
        assert "人工确认" in out["red_line"]

    def test_extract_llm_unavailable(self, db_session):
        import app.services.ai_client as ai_client_mod
        orig = ai_client_mod.ai_chat

        def boom(*a, **k):
            raise RuntimeError("429 rate limited")
        ai_client_mod.ai_chat = boom
        try:
            out = OntologyExtractor(db_session).extract("some report text")
        finally:
            ai_client_mod.ai_chat = orig
        assert out["extracted"] is False
        assert "LLM 不可用" in out["error"]

    def test_empty_text_raises(self, db_session):
        with pytest.raises(ValueError):
            OntologyExtractor(db_session).extract("")
