"""资产域数字员工工具基类（OH-5.1，本体驱动）

定位：通用 ``app/mcp/tools/base.py`` 只解决「带鉴权调后端 + 拆 envelope」；
本基类在其上为资产域工具补齐四件事：

  1. **本体驱动入参**：工具参数 schema 从 ``OntologyClass.attributes`` 声明生成
     （字段名/类型/required/enum），工具不各自手拼散字段——保证 Agent 看到的
     入参始终与资产本体一致，本体演进时工具自动跟随。
  2. **参数校验**：required / 类型 / enum 白名单在调用后端前统一拦截，
     非法入参不产生一次无意义的后端往返。
  3. **统一结果形态**：``ToolResult`` = data + evidence + confidence，
     所有资产域数字员工输出同一形状（主方案 §6.2：证据链 + 置信度）。
  4. **可观测**：每次执行记调用计数（usage 统计），写动作的审计由后端端点
     侧 @log_audit 承担（工具层不重落 hash 链）。

设计见 docs/design/2026-09-30-资产管理AI能力建设方案.md §6。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core import asset_ontology
from app.mcp.tools.base import APIError, call_api

logger = logging.getLogger(__name__)


# 本体 attribute.type → JSON schema 基础类型
_TYPE_MAP: Dict[str, str] = {
    "string": "string",
    "text": "string",
    "uuid": "string",
    "integer": "integer",
    "number": "number",
    "boolean": "boolean",
    "enum": "string",
}


@dataclass(frozen=True)
class ToolResult:
    """资产域工具统一返回。MCP 会将其序列化为 JSON。"""

    data: Any
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    confidence: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "data": self.data,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }


class ToolValidationError(ValueError):
    """工具入参非法（消息可直接返回 Agent）。"""


def schema_for_class(
    class_id: str,
    *,
    include: Optional[tuple[str, ...]] = None,
    extra: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """从本体类 attributes 生成 JSON schema（object）。

    Args:
        class_id: 本体类 id（如 ``asset-instance``）
        include: 仅暴露这些 attribute（缺省全部）
        extra: 追加/覆盖的字段 schema（本体未建模但工具需要的控制参数，
               如分页 page/page_size）

    Returns:
        ``{"type":"object","properties":{...},"required":[...]}``
    """
    ont_class = asset_ontology.get_class(class_id)
    if ont_class is None:
        raise ToolValidationError(f"本体中不存在类：{class_id}")

    properties: Dict[str, Any] = {}
    required: List[str] = []

    for attr in ont_class.attributes:
        attr_id = attr.get("id")
        if not attr_id:
            continue
        if include is not None and attr_id not in include:
            continue

        attr_type = attr.get("type", "string")
        field_schema: Dict[str, Any] = {
            "type": _TYPE_MAP.get(attr_type, "string"),
            "description": attr.get("description", ""),
        }
        if attr_type == "enum" and attr.get("values"):
            field_schema["enum"] = list(attr["values"])
        properties[attr_id] = field_schema

        if attr.get("required"):
            required.append(attr_id)

    if extra:
        for name, spec in extra.items():
            properties[name] = dict(spec)
            if spec.pop("__required", False):
                required.append(name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def validate_params(schema: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
    """按生成的 schema 校验并清洗入参。

    - 丢弃 None / "" （可选过滤参数的「未提供」），保留 False/0
    - required 缺失 → ToolValidationError
    - enum 越界 / 类型不符 → ToolValidationError
    """
    properties = schema.get("properties", {})
    cleaned: Dict[str, Any] = {}

    for name, value in (params or {}).items():
        if name not in properties:
            # 严格模式：不允许本体未声明的字段透传，防止 Agent 拼错参数名还静默忽略
            raise ToolValidationError(f"未知参数：{name}")
        if value is None or value == "":
            continue
        cleaned[name] = value

    for req in schema.get("required", []):
        if req not in cleaned:
            raise ToolValidationError(f"缺少必填参数：{req}")

    for name, value in cleaned.items():
        spec = properties[name]
        expected = spec.get("type")
        if expected == "integer" and not isinstance(value, int):
            raise ToolValidationError(f"参数 {name} 需为整数")
        if expected == "number" and not isinstance(value, (int, float)):
            raise ToolValidationError(f"参数 {name} 需为数字")
        if expected == "boolean" and not isinstance(value, bool):
            raise ToolValidationError(f"参数 {name} 需为布尔值")
        if "enum" in spec and value not in spec["enum"]:
            raise ToolValidationError(
                f"参数 {name} 只能取：{'/'.join(map(str, spec['enum']))}"
            )

    return cleaned


class AssetToolBase:
    """资产域工具基类。

    子类（asset_query_v2 / asset_fusion / asset_audit …）通常只需：
      - 声明 ``name`` / ``description`` / ``class_id``（本体类）
      - 实现 ``build_request(cleaned) -> (method, path, params, body)``
      - 如后端不直接给 evidence，覆写 ``make_evidence(...)``

    通用 CRUD 场景可直接实例化本类（见 build_simple_tool）。
    """

    #: 本体类 id（入参 schema 来源）
    class_id: str = "asset-instance"
    #: 仅暴露的本体字段（None = 全部）
    include_fields: Optional[tuple[str, ...]] = None
    #: 追加的非本体参数（分页等）
    extra_schema: Optional[Dict[str, Dict[str, Any]]] = None

    def __init__(self) -> None:
        self.schema = schema_for_class(
            self.class_id,
            include=self.include_fields,
            extra=dict(self.extra_schema or {}),
        )
        self.invocation_count = 0

    # ---- 子类实现点 ------------------------------------------------------
    def build_request(
        self, cleaned: Dict[str, Any]
    ) -> tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """返回 (method, path, params, json_body)。"""
        raise NotImplementedError

    def make_evidence(
        self,
        cleaned: Dict[str, Any],
        data: Any,
    ) -> List[Dict[str, Any]]:
        """默认无额外证据（后端 payload 自身即依据）。"""
        return []

    # ---- 执行主流程 ------------------------------------------------------
    def run(self, **params: Any) -> ToolResult:
        cleaned = validate_params(self.schema, params)
        method, path, qparams, body = self.build_request(cleaned)

        self.invocation_count += 1
        logger.info(
            "OH-5.1 资产工具执行：%s %s params=%s body_keys=%s",
            method, path, list(qparams or {}), list(body or {}),
        )

        data = call_api(method, path, params=qparams, json_body=body)
        return ToolResult(
            data=data,
            evidence=self.make_evidence(cleaned, data),
        )

    def register(self, mcp) -> None:
        """把本工具注册到 FastMCP（供各 asset_* 工具模块复用）。"""
        tool = self
        mcp.add_tool(
            tool.run,
            name=self.name,
            description=self.description,
        )

    # 供 register 读取（子类必须覆盖 name/description）
    name: str = ""
    description: str = ""


# ---------------------------------------------------------------------------
# 通用 CRUD 工具工厂：无需子类化即可声明一个「读列表/读详情」工具
# ---------------------------------------------------------------------------


class SimpleGetTool(AssetToolBase):
    """通用只读工具：固定 method=GET，路径与参数映射可配置。"""

    def __init__(
        self,
        *,
        name: str,
        description: str,
        path: str,
        class_id: str = "asset-instance",
        include_fields: Optional[tuple[str, ...]] = None,
        extra_schema: Optional[Dict[str, Dict[str, Any]]] = None,
        param_map: Optional[Dict[str, str]] = None,
    ) -> None:
        self.name = name
        self.description = description
        self._path = path
        self.class_id = class_id
        self.include_fields = include_fields
        self.extra_schema = extra_schema
        self._param_map = param_map or {}
        super().__init__()

    def build_request(self, cleaned):
        params: Dict[str, Any] = {}
        for k, v in cleaned.items():
            params[self._param_map.get(k, k)] = v
        return "GET", self._path, params, None
