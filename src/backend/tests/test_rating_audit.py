"""OH-4.12 定级稽核单测（db_session）。"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.business_system import AssetBusiness, BusinessSystem
from app.services.rating_audit import audit, gap_analysis


def _system(db: Session, name: str, **kw) -> BusinessSystem:
    base = dict(code=name, name=name, business_impact="medium",
                data_sensitivity="medium")
    base.update(kw)
    b = BusinessSystem(**base)
    db.add(b)
    db.flush()
    return b


def _member(db: Session, b: BusinessSystem, name: str, pl=None, src="manual", seq=1):
    a = Asset(name=name, asset_ip=f"10.1.{seq}.1", protection_level=pl,
              protection_level_source=src)
    db.add(a)
    db.flush()
    db.add(AssetBusiness(asset_id=a.id, system_id=b.id, role="app"))
    db.flush()
    return a


class TestAudit:
    def test_distribution_and_findings(self, db_session: Session):
        _system(db_session, "unrated-sys")                                # unrated
        s2 = _system(db_session, "pending-sys",
                     rating_status="suggested",
                     suggested_protection_level="level_3",
                     protection_level="level_2")
        _system(db_session, "diverge-sys",
                rating_status="confirmed",
                suggested_protection_level="level_3",
                protection_level="level_1")                              # 差距
        _system(db_session, "ok-sys",
                rating_status="confirmed",
                suggested_protection_level="level_2",
                protection_level="level_2")
        db_session.commit()

        out = audit(db_session)
        assert out["total_systems"] == 4
        assert out["distribution"] == {"unrated": 1, "suggested": 1, "confirmed": 2}
        # 建议覆盖率 = 有 suggested 的 3/4
        assert out["suggestion_coverage"] == 75.0

        kinds = {(f["system_name"], f["kind"]) for f in out["findings"]}
        assert ("unrated-sys", "unrated") in kinds
        assert ("pending-sys", "pending") in kinds
        assert ("diverge-sys", "divergence") in kinds
        assert not any(n == "ok-sys" for n, _ in kinds)
        assert "只建议不裁决" in out["red_line"]

    def test_member_exceeds_system(self, db_session: Session):
        b = _system(db_session, "low-sys", protection_level="level_1",
                    rating_status="confirmed")
        _member(db_session, b, "high-asset", pl="level_3", src="manual", seq=1)
        _member(db_session, b, "ok-asset", pl="level_1", src="inherited", seq=2)
        db_session.commit()

        out = audit(db_session)
        hit = [f for f in out["findings"] if f["kind"] == "member_exceeds_system"]
        assert len(hit) == 1
        assert hit[0]["members"][0]["protection_level"] == "level_3"


class TestGapAnalysis:
    def test_gap_below(self, db_session: Session):
        b = _system(db_session, "g-sys", rating_status="confirmed",
                    suggested_protection_level="level_3",
                    protection_level="level_2")
        _member(db_session, b, "m1", pl=None)
        db_session.commit()

        out = gap_analysis(db_session, b.id)
        assert out["gap"] == "confirmed_below_suggested"
        assert out["consistency"] == "ok"
        assert out["member_summary"]["count"] == 1
        # pl=None 时列默认 level_2/manual（模型 default），不再计入 none
        assert out["member_summary"]["level_sources"]["manual"] == 1
        assert out["system"]["suggested_level"] == "level_3"

    def test_member_exceeds_consistency(self, db_session: Session):
        b = _system(db_session, "g2-sys", protection_level="level_1",
                    rating_status="confirmed")
        _member(db_session, b, "m2", pl="level_4", src="manual")
        db_session.commit()

        out = gap_analysis(db_session, b.id)
        assert out["consistency"] == "member_exceeds_system"
        assert out["member_summary"]["highest_member"]["protection_level"] == "level_4"

    def test_aligned(self, db_session: Session):
        b = _system(db_session, "g3-sys", rating_status="confirmed",
                    suggested_protection_level="level_2",
                    protection_level="level_2")
        db_session.commit()
        assert gap_analysis(db_session, b.id)["gap"] == "aligned"

    def test_missing_system(self, db_session: Session):
        import uuid
        with pytest.raises(LookupError):
            gap_analysis(db_session, uuid.uuid4())
