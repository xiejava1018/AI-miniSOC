"""融合助手（OH-5.3）

让数字员工在身份归属闭环里做三件事（全部复用确认工作台后端，不重写融合逻辑）：
  1. ``list_pending``：列出待人工裁决的身份归属冲突（带真实融合分摘要）
  2. ``get_review``：取一条复核详情——观测 + 全部候选 + 每候选
     ``identity_fusion.FusionResult``（confidence / decision / 因子 / 冲突）
  3. ``resolve``：人工确认后执行 merge / create / dismiss（写动作，
     后端 @log_audit 落 hash 链；工具层不另落审计）

安全边界：
  - 助手默认 **只读**。resolve 必须显式带 decision 且由人确认（description 明示），
    不提供「自动批量裁决」入口——强物理信号冲突不得自动合并。
  - 合并目标必须是该条记录的候选（后端 422 兜底）。

主方案 §6.2：本体对象入参 + 证据链 + 置信度。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.mcp.tools.asset_base import (
    AssetToolBase,
    ToolResult,
    ToolValidationError,
    validate_params,
)

logger = logging.getLogger(__name__)


class FusionPendingTool(AssetToolBase):
    """列出身份归属待复核冲突。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "status": {
            "type": "string",
            "description": "默认 pending；可指定 merged/created/dismissed 查已处理",
            "enum": ["pending", "merged", "created", "dismissed"],
        },
        "page": {"type": "integer", "description": "页码，从 1 开始"},
        "page_size": {"type": "integer", "description": "每页条数（≤200）"},
    }

    name = "asset_fusion_list"
    description = (
        "列出身份归属待复核冲突（多源观测像是同一实体但存在 MAC/硬件等冲突信号）。"
        "返回每条记录的最佳候选融合分 confidence 与冲突因子。默认只看 pending。"
    )

    def build_request(self, cleaned):
        params: Dict[str, Any] = {"status": cleaned.get("status", "pending")}
        if "page" in cleaned:
            params["page"] = cleaned["page"]
        if "page_size" in cleaned:
            params["page_size"] = cleaned["page_size"]
        return "GET", "/assets/attribution/reviews", params, None

    def make_evidence(self, cleaned, data):
        return [{"type": "review_queue", "pending_count": (data or {}).get("pending_count")}]


class FusionDetailTool(AssetToolBase):
    """读取一条归属复核详情（真实融合分 + 全候选）。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "review_id": {
            "type": "string",
            "description": "待复核记录 UUID",
            "__required": True,
        },
    }

    name = "asset_fusion_detail"
    description = (
        "读取一条身份归属复核详情：触发观测、全部候选资产及每候选的真实融合分"
        "（confidence / decision / 参与因子 / 冲突因子 / 阈值）。"
        "用于在人工裁决前看清「为什么判冲突、该合并还是新建」。"
    )

    def build_request(self, cleaned):
        return (
            "GET",
            f"/assets/attribution/reviews/{cleaned['review_id']}",
            None,
            None,
        )

    def make_evidence(self, cleaned, data):
        evidence: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            if data.get("best_score"):
                evidence.append({
                    "type": "fusion_score",
                    "score": data["best_score"],
                })
            if data.get("candidates"):
                evidence.append({
                    "type": "candidates",
                    "candidates": [
                        {
                            "asset_id": c.get("asset_id"),
                            "asset_ip": c.get("asset_ip"),
                            "name": c.get("name"),
                            "confidence": (c.get("score") or {}).get("confidence"),
                            "decision": (c.get("score") or {}).get("decision"),
                        }
                        for c in data["candidates"]
                    ],
                })
        return evidence

    def run(self, **params: Any) -> ToolResult:
        result = super().run(**params)
        if isinstance(result.data, dict) and result.data.get("best_score"):
            result.confidence = result.data["best_score"].get("confidence")
        return result


class FusionResolveTool(AssetToolBase):
    """裁决一条归属复核（写动作，需人工确认）。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "review_id": {
            "type": "string",
            "description": "待复核记录 UUID",
            "__required": True,
        },
        "decision": {
            "type": "string",
            "description": "merge=合并到候选（默认最佳候选）；create=确认不同实体并新建；dismiss=忽略",
            "enum": ["merge", "create", "dismiss"],
            "__required": True,
        },
        "target_asset_id": {
            "type": "string",
            "description": "merge 时可指定非默认候选的 UUID（须在候选范围内）",
        },
        "note": {"type": "string", "description": "可选备注"},
    }

    name = "asset_fusion_resolve"
    description = (
        "【写动作·须人工确认】对一条身份归属复核执行裁决：merge / create / dismiss。"
        "不可自动批量执行；存在 MAC/硬件冲突时不要直接 merge。"
        "操作会落审计。重复裁决返回冲突。"
    )

    def build_request(self, cleaned):
        body: Dict[str, Any] = {"decision": cleaned["decision"]}
        if "target_asset_id" in cleaned:
            body["target_asset_id"] = cleaned["target_asset_id"]
        if "note" in cleaned:
            body["note"] = cleaned["note"]
        return (
            "POST",
            f"/assets/attribution/reviews/{cleaned['review_id']}/resolve",
            None,
            body,
        )

    def make_evidence(self, cleaned, data):
        if isinstance(data, dict):
            return [{
                "type": "resolved",
                "status": data.get("status"),
                "asset_id": data.get("asset_id"),
                "resolved_by": data.get("resolved_by"),
            }]
        return []

    def run(self, **params: Any) -> ToolResult:
        result = super().run(**params)
        if isinstance(result.data, dict):
            score = result.data.get("best_score")
            if isinstance(score, dict):
                result.confidence = score.get("confidence")
        return result


# 单例
_pending_tool = FusionPendingTool()
_detail_tool = FusionDetailTool()
_resolve_tool = FusionResolveTool()


def register(mcp) -> None:
    _pending_tool.register(mcp)
    _detail_tool.register(mcp)
    _resolve_tool.register(mcp)
