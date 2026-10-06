"""闭环编排服务（OH-7.1 · 含 OH-2.6；D-3 合并的单一文件）

把已经各自落地的环节串成一条治理链：

    发现 → 画像 → 定责 → 处置 → 验证 → 复盘
      ↓      ↓      ↓      ↓      ↓      ↓
   多源   AHS   belongs  拾单   复测   权重
   接入  八维   关系    SOAR          反哺（OH-7.3 未建）

本模块是**编排层，不重写任何底层逻辑**：
  - 画像/AHS  → asset_profile.build_profile / ahs_service.compute_ahs
  - 定责关系  → AssetBusiness（belongs）
  - 处置      → remediation_workflow（工单/状态机）
  - 验证      → external_verifier（网络侧独立复测）

提供两类能力：

1. ``loop_status(db)``：闭环态势（只读）
   全量工单按当前所处环节聚合——open/in_progress=处置中、resolved=待验证、
   verified=已闭环、reopened=验证驳回回流；给各环节漏斗计数 + 卡点清单
   （超期未验证 / 多次重开 / 长期未指派）。

2. ``run_loop_for_ticket(db, ticket_id, action, username)``：单工单编排动作
   - ``advance``   推进工单状态（委托 workflow）
   - ``retest``    触发网络侧复测（委托 verifier）
   - ``auto_decide`` 复测已有结论时建议下一步（不静默执行——返回建议动作，
     由人工/调用方确认后再落）。

红线：编排服务不做「自动闭环」——验证通过仍需人工 decide；权重反哺
（第 6 步复盘）在 OH-7.3 落地前，本模块只做事实汇总，不反推权重。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.remediation_ticket import RemediationTicket

logger = logging.getLogger(__name__)

# 闭环环节映射（工单状态 → 所处步骤）
STAGE_DISPATCH = "dispatch"        # open 待指派/处置起点
STAGE_HANDLING = "handling"        # in_progress 处置中
STAGE_VERIFY = "verify"           # resolved 待验证
STAGE_CLOSED = "closed"           # verified 已闭环
STAGE_RETURNED = "returned"       # reopened 验证驳回回流
STAGE_CANCELLED = "cancelled"

_STATUS_TO_STAGE = {
    "open": STAGE_DISPATCH,
    "in_progress": STAGE_HANDLING,
    "resolved": STAGE_VERIFY,
    "verified": STAGE_CLOSED,
    "reopened": STAGE_RETURNED,
    "cancelled": STAGE_CANCELLED,
}

# 卡点：resolved 超过 N 天未验证
VERIFY_SLA_DAYS = 3
# 卡点：reopened 次数（occurrence_count）过多视为反复问题
RECURRING_THRESHOLD = 2


class GovernanceLoopService:
    """治理闭环编排（态势 + 单工单动作）。"""

    def __init__(self, db: Session):
        self.db = db

    # ---------------- 态势 ----------------

    def loop_status(self) -> Dict[str, Any]:
        tickets = self.db.query(RemediationTicket).all()

        stage_dist: Dict[str, int] = {}
        blockers: List[Dict[str, Any]] = []
        for t in tickets:
            stage = _STATUS_TO_STAGE.get(t.status, STAGE_HANDLING)
            stage_dist[stage] = stage_dist.get(stage, 0) + 1

            issue = self._blocker(t)
            if issue:
                blockers.append(issue)

        total = len(tickets)
        closed = stage_dist.get(STAGE_CLOSED, 0)
        # 闭环率（取消的不计入分母——它们不是「该闭环」的）
        denom = total - stage_dist.get(STAGE_CANCELLED, 0)
        close_rate = round(closed * 100.0 / denom, 1) if denom else 0.0

        return {
            "total_tickets": total,
            "stage_distribution": stage_dist,
            "funnel": self._funnel(stage_dist),
            "closed_rate": close_rate,
            "blockers": blockers,
            "blocker_count": len(blockers),
            "red_line": "不自动闭环；验证须人工确认；权重反哺待 OH-7.3",
        }

    # ---------------- 单工单编排 ----------------

    def run_loop_for_ticket(
        self,
        ticket_id: Any,
        action: str,
        username: str,
        *,
        note: Optional[str] = None,
    ) -> Dict[str, Any]:
        ticket = self.db.get(RemediationTicket, ticket_id)
        if ticket is None:
            raise LookupError("工单不存在")

        if action == "advance":
            # 委托：按 to_status 推进（note 里带目标状态）
            if not note:
                raise ValueError("advance 须在 note 提供 to_status")
            from app.services.remediation_workflow import RemediationWorkflowService
            t = RemediationWorkflowService(self.db).advance(
                ticket_id, to_status=note, username=username,
            )
            return {"action": action, "status": t.status,
                    "stage": _STATUS_TO_STAGE.get(t.status)}

        if action == "retest":
            from app.services.external_verifier import ExternalVerifier
            out = ExternalVerifier(self.db).trigger_retest(
                ticket_id, username=username,
                mode=(note or "ports"),
            )
            return {"action": action, **out}

        if action == "suggest_next":
            return self._suggest_next(ticket)

        raise ValueError("action 须为 advance/retest/suggest_next")

    # ---------------- 内部 ----------------

    def _blocker(self, t: RemediationTicket) -> Optional[Dict[str, Any]]:
        # 待验证超期
        if t.status == "resolved":
            ref = t.resolved_at or t.last_activity_at
            if ref and self._aware_naive(ref) < datetime.utcnow() - timedelta(
                days=VERIFY_SLA_DAYS
            ):
                return self._blk(t, "verify_overdue",
                                 f"resolved 超 {VERIFY_SLA_DAYS} 天未验证")
        # 长期未指派
        if t.status == "open" and not (t.assignee or "").strip():
            ref = t.created_at or t.last_activity_at
            if ref and self._aware_naive(ref) < datetime.utcnow() - timedelta(days=2):
                return self._blk(t, "unassigned", "超 2 天未指派责任人")
        # 反复问题
        if (t.occurrence_count or 1) >= RECURRING_THRESHOLD and \
                t.status == "reopened":
            return self._blk(t, "recurring",
                             f"重开 {t.occurrence_count - 1} 次，反复问题")
        return None

    @staticmethod
    def _aware_naive(dt):
        # 比较时统一转 naive（数据库返回可能带 tz，与 utcnow 直接比会炸）
        if dt and dt.tzinfo is not None:
            return dt.replace(tzinfo=None)
        return dt

    @staticmethod
    def _blk(t: RemediationTicket, kind: str, message: str):
        return {
            "ticket_id": str(t.id),
            "title": t.title,
            "status": t.status,
            "kind": kind,
            "message": message,
        }

    @staticmethod
    def _funnel(stage_dist: Dict[str, int]) -> List[Dict[str, Any]]:
        order = [STAGE_DISPATCH, STAGE_HANDLING, STAGE_VERIFY,
                 STAGE_RETURNED, STAGE_CLOSED]
        return [
            {"stage": s, "count": stage_dist.get(s, 0)} for s in order
        ]

    def _suggest_next(self, ticket: RemediationTicket) -> Dict[str, Any]:
        """根据工单当前环节建议下一步（只建议，不执行）。"""
        stage = _STATUS_TO_STAGE.get(ticket.status)
        suggestion: Dict[str, Any]

        if stage == STAGE_DISPATCH:
            suggestion = {"next": "assign",
                          "why": "未指派，先定责任人"}
        elif stage == STAGE_HANDLING:
            suggestion = {"next": "advance_to_resolved",
                          "why": "处置完成后置 resolved"}
        elif stage == STAGE_VERIFY:
            # 有复测结论时按结论建议，否则建议先复测
            from app.services.external_verifier import ExternalVerifier
            ev = ExternalVerifier(self.db).evaluate_retest(ticket.id)
            if ev["verdict"] == "pass":
                suggestion = {"next": "decide_pass",
                              "why": "复测通过，可人工确认 verified"}
            elif ev["verdict"] == "fail":
                suggestion = {"next": "decide_fail",
                              "why": "复测未通过，建议重开",
                              "evidence": ev["message"]}
            else:
                suggestion = {"next": "retest",
                              "why": "尚无复测证据，先触发复测",
                              "detail": ev["message"]}
        elif stage == STAGE_RETURNED:
            suggestion = {"next": "rehandle",
                          "why": "验证驳回，重新处置"}
        else:
            suggestion = {"next": None, "why": "已终态"}

        return {
            "ticket_id": str(ticket.id),
            "stage": stage,
            "suggestion": suggestion,
            "red_line": "只建议下一步，不自动执行",
        }
