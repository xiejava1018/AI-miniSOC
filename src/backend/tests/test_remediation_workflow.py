"""OH-4.6 整改工单服务单测（db_session，独立测试库）。"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import Session

from app.models.asset_reconciliation import AssetReconciliation
from app.models.compliance import ComplianceFinding, ComplianceRun
from app.models.remediation_ticket import (
    STATUS_CANCELLED,
    STATUS_IN_PROGRESS,
    STATUS_OPEN,
    STATUS_RESOLVED,
    STATUS_VERIFIED,
)
from app.services.remediation_workflow import (
    RemediationConflictError,
    RemediationError,
    RemediationWorkflowService,
)


def _make_asset_helper(db: Session):
    from app.models.asset import Asset
    a = Asset(name="f-host", asset_ip="10.9.9.9")
    db.add(a)
    db.flush()
    return a.id


def _recon(db: Session, rtype: str = "shadow") -> AssetReconciliation:
    r = AssetReconciliation(
        run_id=uuid.uuid4(),
        reconciliation_type=rtype,
        details={"freshness": {}},
    )
    db.add(r)
    db.flush()
    return r


def _finding(db: Session, status: str = "fail") -> ComplianceFinding:
    from tests.test_remediation_workflow import _make_asset_helper
    asset_id = _make_asset_helper(db)
    run = ComplianceRun(ruleset_version="v1", rules_total=1, triggered_by="test")
    db.add(run)
    db.flush()
    f = ComplianceFinding(
        run_id=run.id,
        asset_id=asset_id,
        rule_id="SOC-NET-001",
        rule_version=1,
        rule_title="网络分区",
        severity="high",
        status=status,
    )
    db.add(f)
    db.flush()
    return f


class TestCreate:
    def test_create_from_reconciliation(self, db_session: Session):
        r = _recon(db_session)
        svc = RemediationWorkflowService(db_session)
        t = svc.create_from_reconciliation(r, created_by="u1")
        assert t.status == STATUS_OPEN
        assert t.severity == "high"  # shadow → high
        assert "影子资产" in t.title
        assert t.reconciliation_id == r.id

    def test_duplicate_bumps_not_creates(self, db_session: Session):
        r = _recon(db_session)
        svc = RemediationWorkflowService(db_session)
        t1 = svc.create_from_reconciliation(r)
        t2 = svc.create_from_reconciliation(r)
        assert t1.id == t2.id
        assert t2.occurrence_count == 2

    def test_new_ticket_after_terminal(self, db_session: Session):
        r = _recon(db_session)
        svc = RemediationWorkflowService(db_session)
        t1 = svc.create_from_reconciliation(r)
        svc.advance(t1.id, to_status=STATUS_IN_PROGRESS, username="u")
        svc.advance(t1.id, to_status=STATUS_RESOLVED, username="u", note="done")
        svc.advance(t1.id, to_status=STATUS_VERIFIED, username="v")
        t2 = svc.create_from_reconciliation(r)
        assert t2.id != t1.id

    def test_create_from_compliance_finding(self, db_session: Session):
        f = _finding(db_session)
        svc = RemediationWorkflowService(db_session)
        t = svc.create_from_compliance_finding(f)
        assert t.source_type == "compliance"
        assert t.compliance_finding_id == f.id
        assert t.severity == "high"
        assert "SOC-NET-001" in t.title


class TestStateMachine:
    def test_happy_path(self, db_session: Session):
        r = _recon(db_session)
        svc = RemediationWorkflowService(db_session)
        t = svc.create_from_reconciliation(r)
        svc.assign(t.id, assignee="ops", username="admin")
        svc.advance(t.id, to_status=STATUS_IN_PROGRESS, username="ops")
        t = svc.advance(t.id, to_status=STATUS_RESOLVED, username="ops", note="已补录")
        assert t.resolved_by == "ops"
        assert t.resolve_note == "已补录"
        t = svc.advance(t.id, to_status=STATUS_VERIFIED, username="aud")
        assert t.verified_by == "aud"

    def test_illegal_transition(self, db_session: Session):
        r = _recon(db_session)
        svc = RemediationWorkflowService(db_session)
        t = svc.create_from_reconciliation(r)
        with pytest.raises(RemediationConflictError):
            svc.advance(t.id, to_status=STATUS_RESOLVED, username="u")  # open→resolved 非法

    def test_terminal_immutable(self, db_session: Session):
        r = _recon(db_session)
        svc = RemediationWorkflowService(db_session)
        t = svc.create_from_reconciliation(r)
        svc.advance(t.id, to_status=STATUS_CANCELLED, username="u")
        with pytest.raises(RemediationConflictError):
            svc.advance(t.id, to_status=STATUS_IN_PROGRESS, username="u")
        with pytest.raises(RemediationConflictError):
            svc.assign(t.id, assignee="x", username="u")


class TestList:
    def test_filters_and_open_count(self, db_session: Session):
        r1 = _recon(db_session, "shadow")
        r2 = _recon(db_session, "offline")
        svc = RemediationWorkflowService(db_session)
        svc.create_from_reconciliation(r1)
        svc.create_from_reconciliation(r2)

        out = svc.list_tickets()
        assert out["total"] == 2
        assert out["open_count"] == 2
        # 严重度排序：shadow(high) 在前
        assert out["items"][0]["severity"] == "high"

        out2 = svc.list_tickets(source_type="reconciliation", status=STATUS_OPEN)
        assert out2["total"] == 2

    def test_get_missing_raises(self, db_session: Session):
        with pytest.raises(RemediationError):
            RemediationWorkflowService(db_session).get_ticket(uuid.uuid4())
