"""OH-7.2 网络侧独立复测通路单测（db_session）。"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.compliance import ComplianceFinding, ComplianceRun
from app.models.remediation_ticket import RemediationTicket
from app.models.scanner_models import ScannerTask, ScanFinding
from app.models.vulnerability import AssetVulnerability, Vulnerability
from app.services.external_verifier import ExternalVerifier
from app.services.remediation_workflow import RemediationWorkflowService


def _ticket_with_compliance(db: Session, pl_sev="high"):
    a = Asset(name="tgt", asset_ip="10.77.1.10")
    db.add(a)
    db.flush()
    run = ComplianceRun(ruleset_version=1)
    db.add(run)
    db.flush()
    cf = ComplianceFinding(run_id=run.id, asset_id=a.id,
                           rule_id="R1", rule_version=1,
                           rule_title="t", status="fail")
    db.add(cf)
    db.flush()
    t = RemediationWorkflowService(db).create_from_compliance_finding(
        cf, created_by="admin",
    )
    return a, cf, t


class TestTrigger:
    def test_trigger_creates_task(self, db_session: Session):
        a, cf, t = _ticket_with_compliance(db_session)
        db_session.commit()

        out = ExternalVerifier(db_session).trigger_retest(
            t.id, username="admin", mode="ports",
        )
        assert out["target_ip"] == "10.77.1.10"
        assert out["status"] == "pending"
        # 任务真入库
        task = db_session.query(ScannerTask).filter_by(
            run_reason="retest").first()
        assert task is not None

    def test_missing_ticket(self, db_session: Session):
        with pytest.raises(LookupError):
            ExternalVerifier(db_session).trigger_retest(
                uuid.uuid4(), username="admin")

    def test_bad_mode(self, db_session: Session):
        _, _, t = _ticket_with_compliance(db_session)
        db_session.commit()
        with pytest.raises(ValueError):
            ExternalVerifier(db_session).trigger_retest(
                t.id, username="admin", mode="xxx")


class TestEvaluate:
    def test_no_task_inconclusive(self, db_session: Session):
        _, _, t = _ticket_with_compliance(db_session)
        db_session.commit()
        out = ExternalVerifier(db_session).evaluate_retest(t.id)
        assert out["verdict"] == "inconclusive"

    def test_pending_task_inconclusive(self, db_session: Session):
        _, _, t = _ticket_with_compliance(db_session)
        db_session.commit()
        ExternalVerifier(db_session).trigger_retest(t.id, username="admin")
        out = ExternalVerifier(db_session).evaluate_retest(t.id)
        assert out["verdict"] == "inconclusive"
        assert "pending" in out["message"]

    def test_success_clean_pass(self, db_session: Session):
        a, cf, t = _ticket_with_compliance(db_session)
        db_session.commit()
        trig = ExternalVerifier(db_session).trigger_retest(
            t.id, username="admin")
        # 模拟扫描器完成：任务 success、无 finding、无 open 漏洞
        task = db_session.query(ScannerTask).filter_by(
            task_uuid=uuid.UUID(trig["task_uuid"])).first()
        task.status = "success"
        db_session.commit()

        out = ExternalVerifier(db_session).evaluate_retest(t.id)
        assert out["verdict"] == "pass"

    def test_success_with_open_vuln_fail(self, db_session: Session):
        a, cf, t = _ticket_with_compliance(db_session)
        db_session.commit()
        trig = ExternalVerifier(db_session).trigger_retest(
            t.id, username="admin")
        task = db_session.query(ScannerTask).filter_by(
            task_uuid=uuid.UUID(trig["task_uuid"])).first()
        task.status = "success"
        # 该资产仍有 OPEN 漏洞
        v = Vulnerability(cve_id="CVE-R1", title="x", severity="high")
        db_session.add(v)
        db_session.flush()
        db_session.add(AssetVulnerability(
            asset_id=a.id, vulnerability_id=v.id,
            scanner="wazuh", status="open"))
        db_session.commit()

        out = ExternalVerifier(db_session).evaluate_retest(t.id)
        assert out["verdict"] == "fail"
        assert "OPEN 漏洞" in out["message"]

    def test_internal_mode_still_alive_fail(self, db_session: Session):
        a, cf, t = _ticket_with_compliance(db_session)
        db_session.commit()
        trig = ExternalVerifier(db_session).trigger_retest(
            t.id, username="admin", mode="internal")
        task = db_session.query(ScannerTask).filter_by(
            task_uuid=uuid.UUID(trig["task_uuid"])).first()
        task.status = "success"
        db_session.add(ScanFinding(
            scan_task_uuid=task.task_uuid, asset_ip="10.77.1.10",
            exposure="internal"))
        db_session.commit()

        out = ExternalVerifier(db_session).evaluate_retest(t.id)
        assert out["verdict"] == "fail"
        assert "存活" in out["message"]
