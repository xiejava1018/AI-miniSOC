"""整改工单服务（OH-4.6 · S10）

职责：
  - 从两类来源派单：对账差异（pending）、合规 fail 项
  - 责任链流转：assign（指定责任人/期限）→ advance（状态机校验）→ verify
  - 重复派单防护：同来源未终态工单已存在时 bump occurrence_count 而非新建

不做（边界）：
  - 不改对账/合规自身的状态（各自服务管）
  - SOAR 编排、外侧复测（S12 / OH-7.x）
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.asset_reconciliation import AssetReconciliation
from app.models.compliance import ComplianceFinding
from app.models.remediation_ticket import (
    ALLOWED_TRANSITIONS,
    SEVERITY_ORDER,
    SOURCE_COMPLIANCE,
    SOURCE_RECONCILIATION,
    STATUS_IN_PROGRESS,
    STATUS_OPEN,
    STATUS_RESOLVED,
    STATUS_VERIFIED,
    TERMINAL_STATUSES,
    VALID_SOURCES,
    RemediationTicket,
)

logger = logging.getLogger(__name__)


class RemediationError(ValueError):
    """工单操作非法。消息面向调用方。"""


class RemediationConflictError(RemediationError):
    """状态机冲突（非法迁移 / 并发抢占）。"""


# 对账差异类型 → 标题
_RECON_TITLES = {
    "shadow": "影子资产：Wazuh 有 Agent 但台账无记录",
    "offline": "疑似下线：台账有但 Wazuh 侧无 Agent",
    "mismatch": "信息不一致：台账与实际网络不符",
}


class RemediationWorkflowService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------
    # 派单
    # ------------------------------------------------------------------
    def create_from_reconciliation(
        self,
        reconciliation: AssetReconciliation,
        *,
        created_by: str = "system",
        assignee: Optional[str] = None,
        due_at: Optional[datetime] = None,
    ) -> RemediationTicket:
        rtype = reconciliation.reconciliation_type
        title = _RECON_TITLES.get(rtype, f"对账差异：{rtype}")
        detail = {
            "reconciliation_type": rtype,
            "details": reconciliation.details,
            "status_at_creation": reconciliation.status,
        }
        return self._create(
            source_type=SOURCE_RECONCILIATION,
            reconciliation_id=reconciliation.id,
            compliance_finding_id=None,
            asset_id=reconciliation.asset_id,
            title=title,
            severity="high" if rtype == "shadow" else "medium",
            detail=detail,
            created_by=created_by,
            assignee=assignee,
            due_at=due_at,
        )

    def create_from_compliance_finding(
        self,
        finding: ComplianceFinding,
        *,
        created_by: str = "system",
        assignee: Optional[str] = None,
        due_at: Optional[datetime] = None,
    ) -> RemediationTicket:
        title = f"合规不达标：{finding.rule_id} {finding.rule_title or ''}".strip()
        detail = {
            "rule_id": finding.rule_id,
            "rule_title": finding.rule_title,
            "category": finding.category,
            "reason": finding.reason,
            "evidence": finding.evidence,
            "ai_remediation": finding.ai_remediation,
        }
        return self._create(
            source_type=SOURCE_COMPLIANCE,
            reconciliation_id=None,
            compliance_finding_id=finding.id,
            asset_id=finding.asset_id,
            title=title[:200],
            severity=finding.severity or "medium",
            detail=detail,
            created_by=created_by,
            assignee=assignee,
            due_at=due_at,
        )

    def _create(
        self,
        *,
        source_type: str,
        reconciliation_id: Optional[uuid.UUID],
        compliance_finding_id: Optional[uuid.UUID],
        asset_id: Optional[uuid.UUID],
        title: str,
        severity: str,
        detail: Dict[str, Any],
        created_by: str,
        assignee: Optional[str],
        due_at: Optional[datetime],
    ) -> RemediationTicket:
        if source_type not in VALID_SOURCES:
            raise RemediationError(f"未知来源类型：{source_type}")

        # 防重复：同来源未终态工单 → bump
        q = self.db.query(RemediationTicket).filter(
            RemediationTicket.source_type == source_type,
            RemediationTicket.status.notin_(TERMINAL_STATUSES),
        )
        if source_type == SOURCE_RECONCILIATION and reconciliation_id is not None:
            q = q.filter(RemediationTicket.reconciliation_id == reconciliation_id)
        elif source_type == SOURCE_COMPLIANCE and compliance_finding_id is not None:
            q = q.filter(RemediationTicket.compliance_finding_id == compliance_finding_id)
        else:
            raise RemediationError("来源记录 ID 缺失")

        existing = q.first()
        if existing is not None:
            existing.occurrence_count += 1
            existing.last_activity_at = datetime.utcnow()
            self.db.flush()
            logger.info(
                "OH-4.6 工单 bump：ticket=%s source=%s occurrence=%d",
                existing.id, source_type, existing.occurrence_count,
            )
            return existing

        ticket = RemediationTicket(
            source_type=source_type,
            reconciliation_id=reconciliation_id,
            compliance_finding_id=compliance_finding_id,
            asset_id=asset_id,
            title=title,
            severity=severity if severity in SEVERITY_ORDER else "medium",
            detail=detail,
            status=STATUS_OPEN,
            created_by=created_by,
            assignee=assignee,
            due_at=due_at,
            last_activity_at=datetime.utcnow(),
        )
        self.db.add(ticket)
        self.db.flush()
        logger.info("OH-4.6 新工单：ticket=%s source=%s %s", ticket.id, source_type, title)
        return ticket

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def list_tickets(
        self,
        *,
        status: Optional[str] = None,
        source_type: Optional[str] = None,
        assignee: Optional[str] = None,
        asset_id: Optional[uuid.UUID] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        q = self.db.query(RemediationTicket)
        if status:
            q = q.filter(RemediationTicket.status == status)
        if source_type:
            q = q.filter(RemediationTicket.source_type == source_type)
        if assignee:
            q = q.filter(RemediationTicket.assignee == assignee)
        if asset_id is not None:
            q = q.filter(RemediationTicket.asset_id == asset_id)

        total = q.count()
        rows = (
            q.order_by(
                # 严重度降序 → 创建时间升序（老的先处理）
                RemediationTicket.created_at.asc(),
            )
            .offset(max(0, (page - 1) * page_size))
            .limit(page_size)
            .all()
        )
        rows = sorted(rows, key=lambda t: -SEVERITY_ORDER.get(t.severity, 0))

        open_count = (
            self.db.query(RemediationTicket)
            .filter(RemediationTicket.status.notin_(TERMINAL_STATUSES))
            .count()
        )
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "open_count": open_count,
            "items": [self.to_dict(t) for t in rows],
        }

    def get_ticket(self, ticket_id: Any) -> RemediationTicket:
        ticket = self.db.get(RemediationTicket, ticket_id)
        if ticket is None:
            raise RemediationError("工单不存在")
        return ticket

    # ------------------------------------------------------------------
    # 流转
    # ------------------------------------------------------------------
    def assign(
        self,
        ticket_id: Any,
        *,
        assignee: str,
        due_at: Optional[datetime] = None,
        username: str,
    ) -> RemediationTicket:
        ticket = self.get_ticket(ticket_id)
        if ticket.status in TERMINAL_STATUSES:
            raise RemediationConflictError(f"工单已终态（{ticket.status}），不能再指派")
        ticket.assignee = assignee
        if due_at is not None:
            ticket.due_at = due_at
        ticket.last_activity_at = datetime.utcnow()
        self.db.flush()
        return ticket

    def advance(
        self,
        ticket_id: Any,
        *,
        to_status: str,
        username: str,
        note: Optional[str] = None,
    ) -> RemediationTicket:
        ticket = self.get_ticket(ticket_id)
        allowed = ALLOWED_TRANSITIONS.get(ticket.status, set())
        if to_status not in allowed:
            raise RemediationConflictError(
                f"非法状态迁移：{ticket.status} → {to_status}"
                f"（允许：{'/'.join(sorted(allowed)) or '无，已终态'}）"
            )

        now = datetime.utcnow()
        ticket.status = to_status
        ticket.last_activity_at = now
        if to_status == STATUS_RESOLVED:
            ticket.resolved_by = username
            ticket.resolved_at = now
            ticket.resolve_note = note
        elif to_status == STATUS_VERIFIED:
            ticket.verified_by = username
            ticket.verified_at = now
        if note and to_status != STATUS_RESOLVED:
            ticket.resolve_note = note
        self.db.flush()
        logger.info("OH-4.6 工单流转：ticket=%s → %s by %s", ticket.id, to_status, username)
        return ticket

    # ------------------------------------------------------------------
    @staticmethod
    def to_dict(t: RemediationTicket) -> Dict[str, Any]:
        return {
            "id": str(t.id),
            "source_type": t.source_type,
            "reconciliation_id": str(t.reconciliation_id) if t.reconciliation_id else None,
            "compliance_finding_id": str(t.compliance_finding_id) if t.compliance_finding_id else None,
            "asset_id": str(t.asset_id) if t.asset_id else None,
            "title": t.title,
            "severity": t.severity,
            "detail": t.detail,
            "status": t.status,
            "created_by": t.created_by,
            "assignee": t.assignee,
            "due_at": t.due_at.isoformat() if t.due_at else None,
            "resolved_by": t.resolved_by,
            "resolved_at": t.resolved_at.isoformat() if t.resolved_at else None,
            "resolve_note": t.resolve_note,
            "verified_by": t.verified_by,
            "verified_at": t.verified_at.isoformat() if t.verified_at else None,
            "occurrence_count": t.occurrence_count,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        }
