"""OH-4.3 S3 考核资产真实化单测（db_session）。"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.business_system import AssetBusiness, BusinessSystem
from app.models.compliance import ComplianceFinding, ComplianceRun
from app.services.audit_check import scope_audit, system_findings


def _system(db: Session, code: str, **kw) -> BusinessSystem:
    base = dict(code=code, name=code, business_impact="medium",
                data_sensitivity="medium")
    base.update(kw)
    b = BusinessSystem(**base)
    db.add(b)
    db.flush()
    return b


def _member(db: Session, b: BusinessSystem, name: str, seq: int,
            pl="level_2", src="inherited") -> Asset:
    a = Asset(name=name, asset_ip=f"10.2.{seq}.9", protection_level=pl,
              protection_level_source=src)
    db.add(a)
    db.flush()
    db.add(AssetBusiness(asset_id=a.id, system_id=b.id, role="app"))
    db.flush()
    return a


class TestScopeAudit:
    def test_healthy_scope(self, db_session: Session):
        b = _system(db_session, "ok-sys", rating_status="confirmed",
                    protection_level="level_2")
        _member(db_session, b, "m1", 1)
        db_session.commit()

        out = scope_audit(db_session)
        assert out["in_scope_count"] >= 1
        assert out["propagation_gaps"] == []
        assert out["unanchored"] == []
        # 无 finding 时成员进 no_evidence
        assert out["in_scope_no_evidence"][0]["name"] == "m1"

    def test_propagation_gap_detected(self, db_session: Session):
        b = _system(db_session, "hi-sys", rating_status="confirmed",
                    protection_level="level_4")
        _member(db_session, b, "lagging", 2, pl="level_1", src="inherited")
        db_session.commit()

        out = scope_audit(db_session)
        assert len(out["propagation_gaps"]) == 1
        assert out["propagation_gaps"][0]["expected"] == "level_4"

    def test_unanchored_source_inherited_without_system(
        self, db_session: Session
    ):
        # 用不会与其他测试冲突的高地址
        a = Asset(name="orphan-test-xyz", asset_ip="172.31.99.47",
                  protection_level="level_2",
                  protection_level_source="inherited")
        db_session.add(a)
        db_session.flush()

        out = scope_audit(db_session)
        print("DEBUG_UNANCHORED", out["unanchored"])
        hit = [u for u in out["unanchored"]
               if u["name"] == "orphan-test-xyz"]
        assert len(hit) == 1


class TestSystemFindings:
    def test_aggregation_and_rate(self, db_session: Session):
        b = _system(db_session, "audited", rating_status="confirmed",
                    protection_level="level_2")
        a1 = _member(db_session, b, "a1", 3)
        a2 = _member(db_session, b, "a2", 4)
        run = ComplianceRun(ruleset_version=1)
        db_session.add(run)
        db_session.flush()
        now = datetime.utcnow()
        db_session.add_all([
            ComplianceFinding(run_id=run.id, asset_id=a1.id,
                              rule_id="SOC-NET-001", rule_version=1,
                              rule_title="高危端口", status="pass",
                              created_at=now),
            ComplianceFinding(run_id=run.id, asset_id=a2.id,
                              rule_id="SOC-NET-001", rule_version=1,
                              rule_title="高危端口", status="fail",
                              created_at=now),
        ])
        db_session.commit()

        out = system_findings(db_session, b.id)
        assert out["member_count"] == 2
        assert out["by_rule"][0]["pass"] == 1
        assert out["by_rule"][0]["fail"] == 1
        assert out["compliance_rate"] == 50.0

    def test_no_evidence_members(self, db_session: Session):
        b = _system(db_session, "empty", rating_status="confirmed",
                    protection_level="level_2")
        _member(db_session, b, "blind", 5)
        db_session.commit()

        out = system_findings(db_session, b.id)
        assert out["latest_run_at"] is None
        assert out["compliance_rate"] is None
        assert out["no_evidence_assets"][0]["name"] == "blind"

    def test_missing_system(self, db_session: Session):
        with pytest.raises(LookupError):
            system_findings(db_session, uuid.uuid4())
