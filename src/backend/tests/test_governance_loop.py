"""OH-7.1 governance_loop 闭环编排单测（db_session）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.compliance import ComplianceFinding, ComplianceRun
from app.models.remediation_ticket import RemediationTicket
from app.services.governance_loop import (
    GovernanceLoopService,
    STAGE_CLOSED,
    STAGE_DISPATCH,
    STAGE_HANDLING,
    STAGE_RETURNED,
    STAGE_VERIFY,
)
from app.services.remediation_workflow import RemediationWorkflowService


def _ticket(db: Session, status="open", assignee=None, seq=1, **kw) -> RemediationTicket:
    a = Asset(name=f"tgt-{seq}", asset_ip=f"10.91.{seq}.1")
    db.add(a)
    db.flush()
    run = ComplianceRun(ruleset_version=1)
    db.add(run)
    db.flush()
    cf = ComplianceFinding(
        run_id=run.id, asset_id=a.id, rule_id="R1", rule_version=1,
        rule_title="t", status="fail",
    )
    db.add(cf)
    db.flush()
    t = RemediationWorkflowService(db).create_from_compliance_finding(cf)
    t.status = status
    if assignee is not None:
        t.assignee = assignee
    for k, v in kw.items():
        setattr(t, k, v)
    db.flush()
    return t


class TestLoopStatus:
    def test_empty(self, db_session: Session):
        out = GovernanceLoopService(db_session).loop_status()
        assert out["total_tickets"] == 0
        assert out["closed_rate"] == 0.0
        assert out["blockers"] == []

    def test_stage_distribution(self, db_session: Session):
        _ticket(db_session, status="open", seq=1)
        _ticket(db_session, status="in_progress", seq=2)
        _ticket(db_session, status="resolved", seq=3)
        _ticket(db_session, status="verified", seq=4)
        _ticket(db_session, status="cancelled", seq=5)
        db_session.commit()

        out = GovernanceLoopService(db_session).loop_status()
        d = out["stage_distribution"]
        assert d[STAGE_DISPATCH] == 1
        assert d[STAGE_HANDLING] == 1
        assert d[STAGE_VERIFY] == 1
        assert d[STAGE_CLOSED] == 1
        # 分母 4（剔除 cancelled），close_rate = 25.0
        assert out["closed_rate"] == 25.0

    def test_blockers(self, db_session: Session):
        # resolved 超 3 天
        t1 = _ticket(db_session, status="resolved", seq=10)
        t1.resolved_at = datetime.utcnow() - timedelta(days=5)
        # open 超 2 天未指派
        t2 = _ticket(db_session, status="open", assignee=None, seq=11)
        t2.created_at = datetime.utcnow() - timedelta(days=3)
        # reopened 反复
        t3 = _ticket(db_session, status="reopened", occurrence_count=3, seq=12)
        db_session.commit()

        out = GovernanceLoopService(db_session).loop_status()
        kinds = {b["kind"] for b in out["blockers"]}
        assert "verify_overdue" in kinds
        assert "unassigned" in kinds
        assert "recurring" in kinds


class TestRunLoop:
    def test_suggest_next_dispatch(self, db_session: Session):
        t = _ticket(db_session, status="open", assignee=None)
        db_session.commit()
        out = GovernanceLoopService(db_session).run_loop_for_ticket(
            t.id, action="suggest_next", username="admin"
        )
        assert out["stage"] == STAGE_DISPATCH
        assert out["suggestion"]["next"] == "assign"

    def test_suggest_next_verify_inconclusive(self, db_session: Session):
        t = _ticket(db_session, status="resolved")
        db_session.commit()
        out = GovernanceLoopService(db_session).run_loop_for_ticket(
            t.id, action="suggest_next", username="admin"
        )
        # 无复测任务 → inconclusive → 建议先 retest
        assert out["suggestion"]["next"] == "retest"

    def test_advance_action(self, db_session: Session):
        t = _ticket(db_session, status="open", assignee="bob")
        db_session.commit()
        out = GovernanceLoopService(db_session).run_loop_for_ticket(
            t.id, action="advance", username="admin", note="in_progress"
        )
        assert out["status"] == "in_progress"
        assert out["stage"] == STAGE_HANDLING

    def test_advance_missing_note(self, db_session: Session):
        t = _ticket(db_session, status="open")
        db_session.commit()
        with pytest.raises(ValueError):
            GovernanceLoopService(db_session).run_loop_for_ticket(
                t.id, action="advance", username="admin"
            )

    def test_retest_action(self, db_session: Session):
        t = _ticket(db_session, status="resolved")
        db_session.commit()
        out = GovernanceLoopService(db_session).run_loop_for_ticket(
            t.id, action="retest", username="admin", note="ports"
        )
        assert out["status"] == "pending"
        assert out["target_ip"] == "10.91.1.1"

    def test_unknown_action(self, db_session: Session):
        t = _ticket(db_session, status="open")
        db_session.commit()
        with pytest.raises(ValueError):
            GovernanceLoopService(db_session).run_loop_for_ticket(
                t.id, action="xx", username="admin"
            )

    def test_missing_ticket(self, db_session: Session):
        with pytest.raises(LookupError):
            GovernanceLoopService(db_session).run_loop_for_ticket(
                uuid.uuid4(), action="suggest_next", username="admin"
            )
