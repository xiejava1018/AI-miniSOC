"""修复助手（OH-5.6 · S10 数字员工）

包装 OH-4.6 整改工单 API（/assets/remediation/**），不重写工单逻辑：
  - ``asset_remediation_list``   工单列表（状态/来源/责任人过滤 + open_count）
  - ``asset_remediation_detail`` 工单详情（含来源快照与责任链）
  - ``asset_remediation_create`` 从来源派单（对账差异 / 合规 fail 项）
  - ``asset_remediation_assign`` 指派责任人 / 期限
  - ``asset_remediation_advance`` 状态流转（推进/完成/验证/取消）

安全边界：写动作（create/assign/advance）description 明示须人工确认；
不提供自动批量流转；verified 状态预留给 S12 验证回路（OH-4.11）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.mcp.tools.asset_base import AssetToolBase, ToolResult

logger = logging.getLogger(__name__)

_VALID_STATUS = [
    "open", "in_progress", "resolved", "verified", "reopened", "cancelled",
]


class RemediationListTool(AssetToolBase):
    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "status": {"type": "string", "description": "状态过滤", "enum": _VALID_STATUS},
        "source_type": {
            "type": "string",
            "description": "来源过滤",
            "enum": ["reconciliation", "compliance"],
        },
        "assignee": {"type": "string", "description": "责任人用户名"},
        "page": {"type": "integer"},
        "page_size": {"type": "integer"},
    }

    name = "asset_remediation_list"
    description = (
        "列出整改工单（默认全部）：按状态/来源（对账差异/合规 fail 项）/责任人过滤，"
        "返回 open_count 与严重度降序的工单列表。"
    )

    def build_request(self, cleaned):
        params = {k: v for k, v in cleaned.items()}
        return "GET", "/assets/remediation/tickets", params, None

    def make_evidence(self, cleaned, data):
        if isinstance(data, dict):
            return [{
                "type": "ticket_queue",
                "total": data.get("total"),
                "open_count": data.get("open_count"),
            }]
        return []


class RemediationDetailTool(AssetToolBase):
    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "ticket_id": {"type": "string", "description": "工单 UUID", "__required": True},
    }

    name = "asset_remediation_detail"
    description = (
        "读取一张整改工单详情：来源快照（对账差异/合规规则判定）、责任链"
        "（派单人→责任人→处理人→验证人）、当前状态与期限。"
    )

    def build_request(self, cleaned):
        return (
            "GET",
            f"/assets/remediation/tickets/{cleaned['ticket_id']}",
            None,
            None,
        )

    def make_evidence(self, cleaned, data):
        if isinstance(data, dict):
            chain = {
                k: data.get(k)
                for k in ("created_by", "assignee", "resolved_by", "verified_by")
            }
            return [
                {"type": "responsibility_chain", "chain": chain},
                {"type": "source_snapshot", "source_type": data.get("source_type"),
                 "detail": data.get("detail")},
            ]
        return []


class RemediationCreateTool(AssetToolBase):
    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "source_type": {
            "type": "string",
            "description": "来源类型",
            "enum": ["reconciliation", "compliance"],
            "__required": True,
        },
        "source_id": {
            "type": "string",
            "description": "来源记录 UUID（对账差异 ID 或合规 fail 项 ID）",
            "__required": True,
        },
        "assignee": {"type": "string", "description": "可选责任人用户名"},
        "due_at": {"type": "string", "description": "可选整改期限（ISO 时间）"},
    }

    name = "asset_remediation_create"
    description = (
        "【写动作·须人工确认】从来源派整改工单：reconciliation=对账差异，"
        "compliance=合规 fail 项。同来源已有未完结工单时只累计 occurrence 不重复建。"
    )

    def build_request(self, cleaned):
        body: Dict[str, Any] = {
            "source_type": cleaned["source_type"],
            "source_id": cleaned["source_id"],
        }
        if "assignee" in cleaned:
            body["assignee"] = cleaned["assignee"]
        if "due_at" in cleaned:
            body["due_at"] = cleaned["due_at"]
        return "POST", "/assets/remediation/tickets", None, body

    def make_evidence(self, cleaned, data):
        if isinstance(data, dict):
            return [{
                "type": "ticket_created",
                "id": data.get("id"),
                "status": data.get("status"),
                "occurrence_count": data.get("occurrence_count"),
            }]
        return []


class RemediationAssignTool(AssetToolBase):
    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "ticket_id": {"type": "string", "description": "工单 UUID", "__required": True},
        "assignee": {"type": "string", "description": "责任人用户名", "__required": True},
        "due_at": {"type": "string", "description": "可选整改期限（ISO 时间）"},
    }

    name = "asset_remediation_assign"
    description = "【写动作·须人工确认】指派整改工单责任人（可同时设期限）。终态工单不可指派。"

    def build_request(self, cleaned):
        body: Dict[str, Any] = {"assignee": cleaned["assignee"]}
        if "due_at" in cleaned:
            body["due_at"] = cleaned["due_at"]
        return (
            "POST",
            f"/assets/remediation/tickets/{cleaned['ticket_id']}/assign",
            None,
            body,
        )

    def make_evidence(self, cleaned, data):
        if isinstance(data, dict):
            return [{
                "type": "assigned",
                "assignee": data.get("assignee"),
                "due_at": data.get("due_at"),
            }]
        return []


class RemediationAdvanceTool(AssetToolBase):
    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "ticket_id": {"type": "string", "description": "工单 UUID", "__required": True},
        "to_status": {
            "type": "string",
            "description": (
                "目标状态：in_progress=开始处理；resolved=已整改（需 note）；"
                "verified=验证通过；reopened=验证不通过重开；cancelled=误报取消"
            ),
            "enum": ["in_progress", "resolved", "verified", "reopened", "cancelled"],
            "__required": True,
        },
        "note": {"type": "string", "description": "处理说明（resolved 强烈建议填写）"},
    }

    name = "asset_remediation_advance"
    description = (
        "【写动作·须人工确认】推进整改工单状态。状态机：open→in_progress→resolved"
        "→verified；resolved 可 reopened；verified/cancelled 为终态。非法迁移返回 409。"
        "一次只推进一张，不批量。"
    )

    def build_request(self, cleaned):
        body: Dict[str, Any] = {"to_status": cleaned["to_status"]}
        if "note" in cleaned:
            body["note"] = cleaned["note"]
        return (
            "POST",
            f"/assets/remediation/tickets/{cleaned['ticket_id']}/advance",
            None,
            body,
        )

    def make_evidence(self, cleaned, data):
        if isinstance(data, dict):
            return [{
                "type": "advanced",
                "status": data.get("status"),
                "resolved_by": data.get("resolved_by"),
                "verified_by": data.get("verified_by"),
            }]
        return []


# 单例
_tools = (
    RemediationListTool(),
    RemediationDetailTool(),
    RemediationCreateTool(),
    RemediationAssignTool(),
    RemediationAdvanceTool(),
)


def register(mcp) -> None:
    for tool in _tools:
        tool.register(mcp)
