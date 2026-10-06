"""优先级助手（OH-5.5，S5 脆弱性优先级）

S5 完整形态 VPT+ 图谱重排已由 OH-4.5（2026-10-05）落地，本助手现提供：

  - ``asset_priority_overview``：风险总览（分数段分布 + Top10 + 上升最快）
  - ``asset_priority_top_vuln``：按漏洞严重度加权的 Top 资产排行（仅 OPEN）
  - ``asset_priority_system``：业务系统成员排序（等保/业务影响，快速视图）
  - ``asset_priority_vpt_plus``：**VPT+ 修复优先级**——CVSS+攻击路径阻塞
    +业务重要性+暴露可达+在野利用+SLA，消费 GET /vulnerabilities/priority

边界（诚实披露）：``system`` 是轻量排序不含路径；``vpt_plus`` 才是
完整优先级，数据客观缺失（无图谱/无系统）时其对应项中性降级。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.mcp.tools.asset_base import AssetToolBase, ToolResult

logger = logging.getLogger(__name__)

_SYSTEM_NOTE = (
    "轻量排序（等保>业务影响），不含攻击路径；"
    "完整 VPT+ 请用 asset_priority_vpt_plus。"
)

# 等保等级 → 排序权重（level_5 最高）
_PL_ORDER = {"level_5": 5, "level_4": 4, "level_3": 3, "level_2": 2, "level_1": 1}
# 业务影响 5 档（criticality.py 三维口径，BIA）
_BIA_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class PriorityOverviewTool(AssetToolBase):
    """全局风险总览。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema: Dict[str, Dict[str, Any]] = {}

    name = "asset_priority_overview"
    description = (
        "资产风险总览（无需参数）：风险分数段分布、Top10 高风险资产、"
        "评分上升最快的资产。修复排期的全局起点。"
    )

    def build_request(self, cleaned):
        return "GET", "/assets/risk/overview", None, None

    def make_evidence(self, cleaned, data):
        if isinstance(data, dict):
            return [{
                "type": "risk_overview",
                "distribution": data.get("distribution") or data.get("score_distribution"),
                "top": data.get("top10") or data.get("top"),
            }]
        return []


class TopVulnAssetsTool(AssetToolBase):
    """按漏洞严重度加权的 Top 资产。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "limit": {
            "type": "integer",
            "description": "返回条数（1-10，默认 5）",
        },
    }

    name = "asset_priority_top_vuln"
    description = (
        "按未修复（OPEN）漏洞严重度加权的最高风险资产排行：critical 10 分 / "
        "high 5 / medium 2 / low 1。漏洞修复优先级的主要依据。"
    )

    def build_request(self, cleaned):
        return (
            "GET",
            "/vulnerabilities/stats/top-assets",
            {"limit": cleaned.get("limit", 5)},
            None,
        )

    def make_evidence(self, cleaned, data):
        if isinstance(data, list):
            return [{
                "type": "top_vuln_assets",
                "count": len(data),
                "note": "评分口径：critical 10/high 5/medium 2/low 1，仅 OPEN 漏洞",
            }]
        return []


class SystemPriorityTool(AssetToolBase):
    """业务系统视角的修复优先级（降级排序）。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "system_id": {
            "type": "string",
            "description": "业务系统 UUID",
            "__required": True,
        },
    }

    name = "asset_priority_system"
    description = (
        "输入业务系统，输出其成员资产的快速排序（按等保等级 + 业务影响）。"
        "轻量视图不含攻击路径；完整修复优先级用 asset_priority_vpt_plus。"
    )

    def build_request(self, cleaned):
        return "GET", f"/business-systems/{cleaned['system_id']}/assets", None, None

    def run(self, **params: Any) -> ToolResult:
        result = super().run(**params)
        data = result.data
        if isinstance(data, list):
            ranked = self._rank(data)
            result.data = {
                "system_assets": ranked,
                "count": len(ranked),
                "note": _SYSTEM_NOTE,
            }
            # 排序可信度：有等保/业务影响字段支撑的比例
            supported = sum(
                1 for a in ranked if a.get("sort_basis") != "none"
            )
            result.confidence = round(supported / len(ranked), 4) if ranked else None
            result.evidence = [{
                "type": "ranking_basis",
                "basis": "protection_level > business_impact > name",
                "note": _SYSTEM_NOTE,
            }]
        return result

    @staticmethod
    def _rank(assets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        def _key(a: Dict[str, Any]):
            pl = _PL_ORDER.get(a.get("protection_level") or "", 0)
            bia = _BIA_ORDER.get(a.get("business_impact") or "", 0)
            return (-pl, -bia, str(a.get("name") or ""))

        ranked = []
        for a in sorted(assets, key=_key):
            item = dict(a)
            if (a.get("protection_level") or "") in _PL_ORDER:
                item["sort_basis"] = "protection_level"
            elif (a.get("business_impact") or "") in _BIA_ORDER:
                item["sort_basis"] = "business_impact"
            else:
                item["sort_basis"] = "none"
            ranked.append(item)
        return ranked


class VPTPlusTool(AssetToolBase):
    """S5 VPT+ 完整修复优先级。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "system_id": {
            "type": "string",
            "description": "可选：按业务系统圈定范围",
        },
        "limit": {
            "type": "integer",
            "description": "返回条数（1-100，默认 20）",
        },
    }

    name = "asset_priority_vpt_plus"
    description = (
        "VPT+ 脆弱性修复优先级（漏洞太多修不完先修哪个）：综合 CVSS、"
        "攻击路径阻塞性（修一断多）、业务系统重要性、暴露可达性、在野利用、"
        "SLA 超期。纯计算无 LLM；无图谱/无系统的项中性降级，不伪造可达性。"
    )

    def build_request(self, cleaned):
        params: Dict[str, Any] = {
            "limit": cleaned.get("limit", 20),
        }
        if cleaned.get("system_id"):
            params["system_id"] = cleaned["system_id"]
        return "GET", "/vulnerabilities/priority", params, None

    def run(self, **params: Any) -> ToolResult:
        result = super().run(**params)
        if isinstance(result.data, dict):
            ranked = result.data.get("ranked") or []
            result.evidence = [{
                "type": "vpt_plus",
                "total_open": result.data.get("total_open"),
                "graph_method": result.data.get("graph_method"),
                "top": [
                    {"cve": r["vulnerability"]["cve_id"],
                     "score": r["priority_score"]}
                    for r in ranked[:5]
                ],
            }]
            # 置信度：有完整分数的条目占比（数据缺失越少越高）
            if ranked:
                result.confidence = round(
                    sum(1 for r in ranked
                        if r["priority_score"] is not None) / len(ranked), 4
                )
        return result


# 单例
_tools = (
    PriorityOverviewTool(),
    TopVulnAssetsTool(),
    SystemPriorityTool(),
    VPTPlusTool(),
)


def register(mcp) -> None:
    for tool in _tools:
        tool.register(mcp)
