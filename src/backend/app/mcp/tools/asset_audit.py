"""稽核助手（OH-5.4）

复用既有稽核能力，不重写判定逻辑，把两类稽核组织成数字员工可直接消费的工具：

**S4 定级/覆盖率稽核**（全部只读）
  - ``asset_audit_systems``：业务系统清单 + 定级状态分布（unrated / suggested / confirmed）
  - ``asset_audit_coverage``：绑定覆盖率 KPI（关联资产覆盖率，北极星）
  - ``asset_audit_suggest``：对指定业务系统触发等保等级建议（写 suggested_*
    字段，后端 @log_audit；系统只建议不裁决）

**S3 台账真实性稽核**（全部只读）
  - ``asset_audit_data_health``：源健康 + 同步死信 + 对账差异三层总览
  - ``asset_audit_recon_summary``：最近一次台账 vs Wazuh 对账摘要

边界：23 项考核逐项稽核（OH-4.3 audit_check）尚未建设，本助手不伪造该清单；
其落地后在此增补。助手不提供自动整改入口（整改归 OH-5.6）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.mcp.tools.asset_base import AssetToolBase, ToolResult

logger = logging.getLogger(__name__)


class SystemsAuditTool(AssetToolBase):
    """业务系统定级稽核清单。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "rating_status": {
            "type": "string",
            "description": "可选：unrated/suggested/confirmed 过滤",
            "enum": ["unrated", "suggested", "confirmed"],
        },
    }

    name = "asset_audit_systems"
    description = (
        "列出业务系统及其定级状态（未定级/已有等保建议/已确认），用于定级稽核："
        "哪些系统还没有等保等级建议。"
    )

    def build_request(self, cleaned):
        # 后端 GET /business-systems 分页参数为 page/page_size，不支持 rating_status
        # 过滤；rating_status 仅用于本工具客户端过滤，故不放入 query。
        return "GET", "/business-systems", {"page": 1, "page_size": 100}, None

    def make_evidence(self, cleaned, data):
        items = (data or {}).get("items") if isinstance(data, dict) else None
        counts: Dict[str, int] = {}
        for it in items or []:
            status = it.get("rating_status", "unrated")
            counts[status] = counts.get(status, 0) + 1
        return [{"type": "rating_status_distribution", "distribution": counts}]


class CoverageAuditTool(AssetToolBase):
    """绑定覆盖率 KPI。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema: Dict[str, Dict[str, Any]] = {}

    name = "asset_audit_coverage"
    description = (
        "资产绑定业务系统的覆盖率稽核（无需参数）：返回关联资产数/总资产数/"
        "覆盖率、业务系统数、未定级与待确认建议数。"
    )

    def build_request(self, cleaned):
        return "GET", "/business-systems/coverage-kpi", None, None

    def make_evidence(self, cleaned, data):
        if isinstance(data, dict):
            return [{"type": "coverage_kpi", "coverage_rate": data.get("coverage_rate")}]
        return []

    def run(self, **params: Any) -> ToolResult:
        result = super().run(**params)
        if isinstance(result.data, dict):
            rate = result.data.get("coverage_rate")
            # 覆盖率本身即可信度参照（百分比 → 0-1）
            result.confidence = round(rate / 100.0, 4) if isinstance(rate, (int, float)) else None
        return result


class ProtectionSuggestTool(AssetToolBase):
    """对业务系统触发等保等级建议（S4，只建议）。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "system_id": {
            "type": "string",
            "description": "业务系统 UUID",
            "__required": True,
        },
    }

    name = "asset_audit_suggest_level"
    description = (
        "【写动作·只建议不裁决】对指定业务系统生成等保等级建议，写入"
        "suggested_protection_level 与 suggestion_basis（可解释依据）。"
        "建议须经确认工作台人工确认，系统不自动定级。"
    )

    def build_request(self, cleaned):
        return (
            "POST",
            f"/business-systems/{cleaned['system_id']}/suggest-protection-level",
            None,
            {},
        )

    def make_evidence(self, cleaned, data):
        if isinstance(data, dict):
            return [{
                "type": "suggestion_basis",
                "suggested_level": data.get("suggested_protection_level"),
                "basis": data.get("suggestion_basis"),
            }]
        return []


class DataHealthAuditTool(AssetToolBase):
    """S3 数据真实性三层健康稽核。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "dead_letter_limit": {
            "type": "integer",
            "description": "死信样本条数（0-50，默认 5）",
        },
    }

    name = "asset_audit_data_health"
    description = (
        "台账真实性稽核（无需参数）：源健康（采集器是否正常）、同步死信"
        "（被丢弃数据）、对账差异（台账与实际网络）三层总览。"
    )

    def build_request(self, cleaned):
        params = {"dead_letter_limit": cleaned.get("dead_letter_limit", 5)}
        return "GET", "/data-health", params, None

    def make_evidence(self, cleaned, data):
        if isinstance(data, dict):
            return [{
                "type": "health_overview",
                "summary": data.get("summary"),
            }]
        return []


class ReconSummaryAuditTool(AssetToolBase):
    """最近一次对账摘要。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema: Dict[str, Dict[str, Any]] = {}

    name = "asset_audit_recon_summary"
    description = (
        "最近一次台账 vs Wazuh Agent 对账摘要（无需参数）：影子/掉线/信息不一致"
        "差异分布与数据新鲜度，用于台账真实性稽核。"
    )

    def build_request(self, cleaned):
        return "GET", "/assets/reconcile/summary", None, None

    def make_evidence(self, cleaned, data):
        if isinstance(data, dict):
            return [{"type": "recon_summary",
                     "by_type": data.get("by_type"),
                     "pending_total": data.get("pending_total"),
                     "freshness": data.get("freshness")}]
        return []


# 单例
_tools = (
    SystemsAuditTool(),
    CoverageAuditTool(),
    ProtectionSuggestTool(),
    DataHealthAuditTool(),
    ReconSummaryAuditTool(),
)


def register(mcp) -> None:
    for tool in _tools:
        tool.register(mcp)
