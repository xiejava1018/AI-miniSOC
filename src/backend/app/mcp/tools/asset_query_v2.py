"""资产问答·本体驱动版（OH-5.2）

与既有 L1/L2 能力的关系（不重写问答引擎）：
  - 问句解析 / L1 筛选 / L2 模板执行 / 多轮会话全部复用
    ``POST /assets/ask``（AssetQueryService）。
  - 本模块做的是「本体驱动的工具外壳」：
      * 入参用本体术语声明（question + 可选 session_id，经基类校验）
      * 把 /ask 的 payload 映射为统一 ToolResult
      * 从 payload 提取 **置信度**（融合/模板语义）与 **证据**（模板名/参数/覆盖率/
        告警分桶），让 Agent 能判断结论可不可信、依据是什么
      * 透传诚实降级（unavailable / unsupported / invalid_params），不包装成成功

主方案 §6.2：工具输出 = 证据链 + 置信度。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.mcp.tools.asset_base import AssetToolBase, ToolResult

logger = logging.getLogger(__name__)


# 置信度按问答结果形态给出（工具层启发式，不替代融合分；融合分在 OH-5.3 使用）
_INTENT_CONFIDENCE: Dict[str, Optional[float]] = {
    # 正常命中：L2 模板执行是确定逻辑，置信度高
    "template": 0.9,
    "filter": 0.75,
    "stats": 0.75,
    "detail": 0.75,
    # 非成功形态
    "unsupported": None,
    "unavailable": None,
    "invalid_params": None,
    "error": None,
}


class AssetQueryV2Tool(AssetToolBase):
    """asset_query 本体驱动版。

    入参本体类沿用 asset-instance，但问答工具的入参是「问句」而非资产属性，
    故不暴露 asset-instance 的属性（include_fields=() 全部排除），
    只通过 extra_schema 声明 question/session_id。
    """

    class_id = "asset-instance"
    include_fields = ()  # 不暴露资产属性
    extra_schema = {
        "question": {
            "type": "string",
            "description": "用中文提出的资产问题，如「哪些资产开放了 3389 端口？」",
            "__required": True,
        },
        "session_id": {
            "type": "string",
            "description": "可选，传入以续接多轮会话",
        },
    }

    name = "asset_query"
    description = (
        "资产自然语言问答（本体驱动）。支持资产筛选、开放端口、掉线设备、"
        "资产近期告警、按维度分组统计、高危/漏洞/过保资产、责任人/业务系统查询等。"
        "返回统一结果：data 内含 L1/L2 结论与摘要，evidence 给出模板/参数/覆盖率依据，"
        "confidence 反映结论可信度；AI 不可用或问句超范围时 data.intent 会如实标明。"
    )

    def build_request(self, cleaned):
        body: Dict[str, Any] = {
            "question": cleaned["question"],
            "session_id": cleaned.get("session_id"),
        }
        return "POST", "/assets/ask", None, body

    def make_evidence(self, cleaned, data):
        return _evidence_from_payload(data)

    def run(self, **params: Any) -> ToolResult:
        result = super().run(**params)
        payload = result.data if isinstance(result.data, dict) else {}
        result.confidence = _confidence_from_payload(payload)
        return result


def _evidence_from_payload(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """把 /ask 回显的可核对信息提炼为证据条目。"""
    evidence: List[Dict[str, Any]] = []
    intent = payload.get("intent")

    if payload.get("template_id"):
        evidence.append({
            "type": "query_template",
            "template_id": payload["template_id"],
            "template_name": payload.get("template_name"),
            "templates_version": payload.get("templates_version"),
            "params": payload.get("params"),
        })
    elif payload.get("params"):
        evidence.append({"type": "l1_filters", "params": payload["params"]})

    coverage = payload.get("coverage")
    if coverage:
        evidence.append({"type": "data_coverage", **coverage})

    alerts = payload.get("alerts")
    if alerts:
        evidence.append({"type": "alert_buckets", "alerts": alerts})

    if payload.get("notes"):
        evidence.append({"type": "notes", "notes": payload["notes"]})

    # 非成功形态也记录（让 Agent 知道为什么没结论，而不是拿到空 evidence）
    if intent in ("unsupported", "unavailable", "invalid_params", "error"):
        evidence.append({
            "type": "non_success",
            "intent": intent,
            "message": payload.get("message") or payload.get("summary"),
        })

    return evidence


def _confidence_from_payload(payload: Dict[str, Any]) -> Optional[float]:
    intent = payload.get("intent")
    return _INTENT_CONFIDENCE.get(intent)


# 单例（register 用；测试也可引用同一实例）
asset_query_v2_tool = AssetQueryV2Tool()


def register(mcp) -> None:
    asset_query_v2_tool.register(mcp)
