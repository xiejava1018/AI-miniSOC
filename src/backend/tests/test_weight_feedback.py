"""OH-7.3 权重学习报告单测（db_session）。"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.compliance import ComplianceFinding, ComplianceRun
from app.models.remediation_ticket import RemediationTicket
from app.services.remediation_workflow import RemediationWorkflowService
from app.services.weight_feedback import (
    MIN_SAMPLE,
    WeightFeedbackService,
)


def _verified(db: Session, seq: int, source="compliance",
              severity="high") -> RemediationTicket:
    a = Asset(name=f"wfg-{seq}", asset_ip=f"10.95.{seq}.1")
    db.add(a)
    db.flush()
    run = ComplianceRun(ruleset_version=1)
    db.add(run)
    db.flush()
    cf = ComplianceFinding(
        run_id=run.id, asset_id=a.id, rule_id=f"R{seq}",
        rule_version=1, rule_title="t", status="fail",
    )
    db.add(cf)
    db.flush()
    t = RemediationWorkflowService(db).create_from_compliance_finding(cf)
    t.status = "verified"
    t.severity = severity
    db.flush()
    return t


class TestReport:
    def test_below_min_sample(self, db_session: Session):
        _verified(db_session, seq=1)
        db_session.commit()
        out = WeightFeedbackService(db_session).report()
        assert out["total_verified"] == 1
        assert out["sample_sufficient"] is False
        assert "样本不足" in out["message"]

    def test_dimension_breakdown(self, db_session: Session):
        # 30 高 + 5 低，compliance 维 high_ratio 较高
        for i in range(1, 30 + 1):
            _verified(db_session, seq=i, severity="high")
        for i in range(31, 36):
            _verified(db_session, seq=i, severity="low")
        db_session.commit()

        out = WeightFeedbackService(db_session).report()
        assert out["total_verified"] == 35
        assert out["sample_sufficient"] is True
        comp = out["by_dimension"]["compliance"]
        # 30/35 ≈ 85.7%
        assert comp["count"] == 35
        assert comp["high_ratio"] >= 85.0

    def test_suggestions_with_high_ratio(self, db_session: Session):
        for i in range(1, 31):
            _verified(db_session, seq=i, severity="critical")
        db_session.commit()
        out = WeightFeedbackService(db_session).report()
        sugg = out["suggestions"]
        assert any(s["dimension"] == "compliance"
                   and s["direction"] == "up" for s in sugg)

    def test_red_line_present(self, db_session: Session):
        _verified(db_session, seq=1)
        db_session.commit()
        out = WeightFeedbackService(db_session).report()
        assert "建议是参考" in out["red_line"]
        assert "current_weights" in out  # 当前权重常量只读快照
