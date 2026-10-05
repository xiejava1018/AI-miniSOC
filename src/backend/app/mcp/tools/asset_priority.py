"""优先级助手（OH-5.5，S5 脆弱性优先级 · 降级版）

S5 完整形态是 VPT+ 图谱重排（OH-4.5，pending）——以漏洞可达性/暴露路径
重排修复优先级。当前降级版复用既有评分与排行能力：

  - ``asset_priority_overview``：风险总览（分数段分布 + Top10 + 上升最快）
  - ``asset_priority_top_vuln``：按漏洞严重度加权的 Top 资产排行（仅 OPEN 漏洞）
  - ``asset_priority_system``：业务系统视角——成员资产按业务影响/等保等级/角色
    排序，给出修复顺序建议（弱排序，不冒充 VPT+）

降级边界（诚实披露）：本工具不重排暴露路径可达性；OH-4.5 落地后
``asset_priority_system`` 升级为 VPT+ 排序。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List

from app.mcp.tools.asset_base import AssetToolBase, ToolResult

logger = logging.getLogger(__name__)

_DEGRADATION_NOTE = (
    "当前为降级版排序（业务影响/等保/漏洞加权），未含暴露路径可达性重排；"
    "OH-4.5 VPT+ 落地后升级。"
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
        "输入业务系统，输出其成员资产的修复优先级排序（按等保等级 + 业务影响 + 角色）。"
        "降级版：不含暴露路径可达性重排（VPT+ 待建）；每资产建议用 "
        "asset_query / get_asset 进一步取风险明细。"
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
                "note": _DEGRADATION_NOTE,
            }
            # 排序可信度：有等保/业务影响字段支撑的比例
            supported = sum(
                1 for a in ranked if a.get("sort_basis") != "none"
            )
            result.confidence = round(supported / len(ranked), 4) if ranked else None
            result.evidence = [{
                "type": "ranking_basis",
                "basis": "protection_level > business_impact > name",
                "degradation": _DEGRADATION_NOTE,
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


# 单例
_tools = (
    PriorityOverviewTool(),
    TopVulnAssetsTool(),
    SystemPriorityTool(),
)


def register(mcp) -> None:
    for tool in _tools:
        tool.register(mcp)
