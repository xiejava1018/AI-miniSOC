"""OH-5.1 资产域工具基类单测。

覆盖：
  - schema_for_class：本体 attributes → JSON schema（required/enum/type）
  - validate_params：required 缺失 / enum 越界 / 未知参数 / 空值过滤
  - SimpleGetTool：build_request 参数映射
  - AssetToolBase.run：mock call_api，验证统一 ToolResult 形态与调用计数
不连后端（monkeypatch call_api）。
"""
from __future__ import annotations

import pytest

from app.mcp.tools import asset_base
from app.mcp.tools.asset_base import (
    AssetToolBase,
    SimpleGetTool,
    ToolValidationError,
    schema_for_class,
    validate_params,
)


class TestSchemaGeneration:
    def test_schema_from_asset_instance(self):
        schema = schema_for_class("asset-instance", include=("asset_ip", "uuid"))
        assert schema["type"] == "object"
        assert set(schema["properties"]) == {"asset_ip", "uuid"}
        assert "uuid" in schema["required"]
        assert schema["properties"]["asset_ip"]["type"] == "string"

    def test_extra_fields(self):
        schema = schema_for_class(
            "asset-instance",
            include=("asset_ip",),
            extra={"page": {"type": "integer", "__required": True}},
        )
        assert schema["properties"]["page"]["type"] == "integer"
        assert "page" in schema["required"]

    def test_unknown_class_raises(self):
        with pytest.raises(ToolValidationError):
            schema_for_class("no-such-class")


class TestValidate:
    def test_unknown_param_rejected(self):
        schema = schema_for_class("asset-instance", include=("asset_ip",))
        with pytest.raises(ToolValidationError, match="未知参数"):
            validate_params(schema, {"bogus": "1.1.1.1"})

    def test_missing_required(self):
        schema = schema_for_class("asset-instance", include=("uuid",))
        with pytest.raises(ToolValidationError, match="必填"):
            validate_params(schema, {})

    def test_empty_values_dropped(self):
        # network_zone 非必填 → "" 被当作未提供丢弃；必填字段传空会在后续必填检查拦截
        schema = schema_for_class("asset-instance", include=("network_zone",))
        out = validate_params(schema, {"network_zone": ""})
        assert "network_zone" not in out

    def test_required_empty_value_still_rejected(self):
        schema = schema_for_class("asset-instance", include=("asset_ip",))
        with pytest.raises(ToolValidationError, match="必填"):
            validate_params(schema, {"asset_ip": ""})

    def test_falsey_values_kept(self):
        schema = schema_for_class(
            "asset-instance",
            include=("asset_ip",),
            extra={"enabled": {"type": "boolean"}},
        )
        out = validate_params(schema, {"asset_ip": "1.1.1.1", "enabled": False})
        assert out["enabled"] is False

    def test_type_mismatch(self):
        schema = schema_for_class(
            "asset-instance",
            include=("asset_ip",),
            extra={"page": {"type": "integer"}},
        )
        with pytest.raises(ToolValidationError):
            validate_params(schema, {"asset_ip": "1.1.1.1", "page": "two"})

    def test_enum_enforced(self):
        schema = schema_for_class(
            "asset-instance",
            include=("asset_ip",),
            extra={"zone": {"type": "string", "enum": ["a", "b"]}},
        )
        with pytest.raises(ToolValidationError):
            validate_params(schema, {"asset_ip": "1.1.1.1", "zone": "c"})
        out = validate_params(schema, {"asset_ip": "1.1.1.1", "zone": "a"})
        assert out["zone"] == "a"


class TestSimpleGetTool:
    def test_build_request_and_param_map(self):
        tool = SimpleGetTool(
            name="find_by_ip",
            description="t",
            path="/assets",
            include_fields=("asset_ip",),
            extra_schema={"page": {"type": "integer"}},
            param_map={"asset_ip": "ip"},
        )
        method, path, params, body = tool.build_request(
            {"asset_ip": "10.0.0.1", "page": 2}
        )
        assert method == "GET"
        assert path == "/assets"
        assert params == {"ip": "10.0.0.1", "page": 2}
        assert body is None


class _DummyTool(AssetToolBase):
    class_id = "asset-instance"
    include_fields = ("asset_ip",)
    name = "dummy"
    description = "dummy tool"

    def build_request(self, cleaned):
        return "GET", "/assets", dict(cleaned), None


class TestToolRun:
    def test_run_returns_tool_result(self, monkeypatch):
        monkeypatch.setattr(
            asset_base, "call_api",
            lambda m, p, params=None, json_body=None: {"total": 1},
        )
        tool = _DummyTool()
        result = tool.run(asset_ip="10.0.0.1")

        assert result.data == {"total": 1}
        assert result.evidence == []
        assert result.confidence is None
        assert tool.invocation_count == 1

    def test_run_invalid_params_no_api_call(self, monkeypatch):
        called = {"n": 0}

        def _api(*a, **k):
            called["n"] += 1

        monkeypatch.setattr(asset_base, "call_api", _api)
        tool = _DummyTool()
        with pytest.raises(ToolValidationError):
            tool.run(unknown_field="x")
        assert called["n"] == 0
        assert tool.invocation_count == 0
