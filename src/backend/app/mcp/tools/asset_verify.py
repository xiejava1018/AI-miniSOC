"""验证助手（OH-5.7 · S12）

S12 验证能力（OH-7.2 复测通路 2026-10-05 落地）：

  - ``asset_verify_queue``：待验证工单队列 + 回单质检（缺说明/超期/重复）
  - ``asset_verify_retest``：触发/查看网络侧独立复测——对 resolved 工单建
    扫描任务并回取结论（pass/fail/inconclusive），缺证据不判达标
  - ``asset_verify_decide``：人工验证结论落地——verified / reopened

边界（诚实披露）：复测是**网络侧独立复测**（端口/漏洞），非互联网
外部攻击者视角；自动 reopen 的最终决策权在人工（decide），复测 fail
    只给信号不静默改状态。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from app.mcp.tools.asset_base import AssetToolBase, ToolResult

logger = logging.getLogger(__name__)

_QUEUE_NOTE = (
    "回单质检依据为工单元数据（说明/期限/重复）；"
    "网络侧复测请用 asset_verify_retest。"
)


class VerifyQueueTool(AssetToolBase):
    """待验证工单队列 + 回单质检。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "assignee": {"type": "string", "description": "可选：按责任人过滤"},
        "page": {"type": "integer"},
        "page_size": {"type": "integer", "description": "默认 20，≤200"},
    }

    name = "asset_verify_queue"
    description = (
        "列出待验证（已整改、未验证）的整改工单，并对每张做回单质检："
        "是否缺处理说明、是否超期、是否重复触发（同一问题多次出现）。"
        "输出质量信号辅助人工验证决策。"
    )

    def build_request(self, cleaned):
        params: Dict[str, Any] = {"status": "resolved"}
        if "assignee" in cleaned:
            params["assignee"] = cleaned["assignee"]
        if "page" in cleaned:
            params["page"] = cleaned["page"]
        if "page_size" in cleaned:
            params["page_size"] = cleaned["page_size"]
        return "GET", "/assets/remediation/tickets", params, None

    def run(self, **params: Any) -> ToolResult:
        result = super().run(**params)
        data = result.data
        if isinstance(data, dict):
            items = data.get("items") or []
            flagged = [self._check(t) for t in items]
            n_flag = sum(1 for f in flagged if f["quality_issues"])
            result.data = {
                "total": data.get("total"),
                "awaiting_verification": len(items),
                "flagged": n_flag,
                "items": flagged,
                "note": _QUEUE_NOTE,
            }
            # 队列可信度：无质量问题的工单占比（全无说明 → None）
            result.confidence = (
                round((len(items) - n_flag) / len(items), 4) if items else None
            )
            result.evidence = [{
                "type": "quality_check",
                "rules": [
                    "missing_note: resolved 无处理说明",
                    "overdue: due_at 已过仍未验证",
                    "recurring: occurrence_count > 1（问题重复出现）",
                ],
                "flagged": n_flag,
            }]
        return result

    @staticmethod
    def _check(ticket: Dict[str, Any]) -> Dict[str, Any]:
        issues: List[str] = []
        if not (ticket.get("resolve_note") or "").strip():
            issues.append("missing_note")
        due = ticket.get("due_at")
        if due:
            try:
                due_dt = datetime.fromisoformat(str(due).replace("Z", "+00:00"))
                if due_dt < datetime.now(timezone.utc):
                    issues.append("overdue")
            except ValueError:
                pass
        if (ticket.get("occurrence_count") or 0) > 1:
            issues.append("recurring")
        out = dict(ticket)
        out["quality_issues"] = issues
        return out


class VerifyDecideTool(AssetToolBase):
    """验证结论落地（verified / reopened）。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "ticket_id": {"type": "string", "description": "工单 UUID", "__required": True},
        "verdict": {
            "type": "string",
            "description": "pass=验证通过（verified）；fail=不通过重开（reopened）",
            "enum": ["pass", "fail"],
            "__required": True,
        },
        "note": {"type": "string", "description": "验证说明（fail 时建议写复测依据）"},
    }

    name = "asset_verify_decide"
    description = (
        "【写动作·须人工确认】对已整改工单给出验证结论：pass→verified（终态），"
        "fail→reopened（重开回到处理流）。验证前建议先看 asset_verify_queue 的"
        "质量信号。不批量执行。"
    )

    def build_request(self, cleaned):
        to_status = "verified" if cleaned["verdict"] == "pass" else "reopened"
        body: Dict[str, Any] = {"to_status": to_status}
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
                "type": "verdict",
                "verdict": cleaned.get("verdict"),
                "status": data.get("status"),
                "verified_by": data.get("verified_by"),
            }]
        return []


class VerifyRetestTool(AssetToolBase):
    """网络侧独立复测：触发并回取结论。"""

    class_id = "asset-instance"
    include_fields = ()
    extra_schema = {
        "ticket_id": {"type": "string", "description": "工单 UUID",
                      "__required": True},
        "action": {
            "type": "string",
            "description": "trigger=触发复测；evaluate=只看已有结论（默认 evaluate）",
            "enum": ["trigger", "evaluate"],
        },
        "mode": {
            "type": "string",
            "description": "trigger 时复测类型：ports(默认)/internal",
            "enum": ["ports", "internal"],
        },
    }

    name = "asset_verify_retest"
    description = (
        "网络侧独立复测：action=trigger 对已整改工单建扫描任务（从网络侧重测"
        "端口/漏洞），action=evaluate 回取结论（pass/fail/inconclusive）。"
        "缺证据不判达标；非互联网外部视角。复测 fail 请用 asset_verify_decide"
        "(verdict=fail) 重开。"
    )

    def build_request(self, cleaned):
        tid = cleaned["ticket_id"]
        if cleaned.get("action", "evaluate") == "trigger":
            body: Dict[str, Any] = {
                "mode": cleaned.get("mode", "ports"),
            }
            return "POST", f"/assets/remediation/tickets/{tid}/retest", None, body
        return "GET", f"/assets/remediation/tickets/{tid}/retest", None, None

    def make_evidence(self, cleaned, data):
        if isinstance(data, dict):
            return [{
                "type": "retest",
                "verdict": data.get("verdict"),
                "task_status": data.get("task_status"),
                "target_ip": data.get("target_ip"),
            }]
        return []

    def run(self, **params: Any) -> ToolResult:
        result = super().run(**params)
        if isinstance(result.data, dict) and result.data.get("verdict"):
            v = result.data["verdict"]
            result.confidence = {"pass": 0.9, "fail": 0.85}.get(v, None)
        return result


# 单例
_queue_tool = VerifyQueueTool()
_retest_tool = VerifyRetestTool()
_decide_tool = VerifyDecideTool()


def register(mcp) -> None:
    _queue_tool.register(mcp)
    _retest_tool.register(mcp)
    _decide_tool.register(mcp)
