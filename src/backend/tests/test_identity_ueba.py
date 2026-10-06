"""OH-2.8 行为维 UEBA 单测（db_session + 纯函数）。"""
from __future__ import annotations

from datetime import datetime, timedelta, date

import pytest
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.behavior_profile import BehaviorProfile
from app.models.identity import IdentityEvent
from app.services.identity_ueba import detect_zombies, score_behavior_anomaly, zombie_clearance_rate


def _profile(**kw) -> BehaviorProfile:
    base = dict(
        profile_date=date(2026, 10, 5),
        status="ok", total=100, traffic_type="human",
        by_hour=[5] * 24, workday=90, weekend=10,
        tags=[], layer_visit={}, top_domains=[],
    )
    base.update(kw)
    return BehaviorProfile(**base)


class TestAnomalyScore:
    def test_no_snapshot_neutral(self):
        out = score_behavior_anomaly(None)
        assert out["anomaly_score"] is None
        assert out["basis"] == "no_snapshot"

    def test_gap_day_neutral(self):
        out = score_behavior_anomaly(_profile(status="gap"))
        assert out["anomaly_score"] is None
        assert out["basis"] == "data_gap"

    def test_zero_traffic_zero_score(self):
        out = score_behavior_anomaly(_profile(total=0))
        assert out["anomaly_score"] == 0
        assert out["basis"] == "zero_traffic"

    def test_normal_day_low_score(self):
        out = score_behavior_anomaly(_profile(
            by_hour=[0] * 7 + [12] * 17,  # 全工作时段
            weekend=0, workday=100,
        ))
        assert out["anomaly_score"] == 0
        assert out["signals"] == []

    def test_night_ratio_signal(self):
        # 夜间 50/100
        out = score_behavior_anomaly(_profile(
            by_hour=[8, 8, 8, 8, 8, 5, 5] + [0] * 17,
            weekend=0, workday=100,
        ))
        assert out["anomaly_score"] == 30
        assert out["signals"][0]["kind"] == "night_activity"

    def test_weekend_and_type_mismatch(self):
        out = score_behavior_anomaly(
            _profile(
                by_hour=[0] * 7 + [20] * 17, weekend=60, workday=40,
                traffic_type="human",
            ),
            asset_type="server",  # 服务器上人类流量 → 错配
        )
        kinds = {s["kind"] for s in out["signals"]}
        assert "weekend_activity" in kinds
        assert "traffic_type_mismatch" in kinds
        assert out["anomaly_score"] == 45

    def test_risky_tags(self):
        out = score_behavior_anomaly(_profile(
            by_hour=[0] * 7 + [50] * 17,
            tags=[{"name": "夜间活跃"}, {"name": "正常"}],
        ))
        kinds = {s["kind"] for s in out["signals"]}
        assert "risky_tags" in kinds
        assert out["anomaly_score"] >= 15


class TestZombies:
    def test_zombie_detected(self, db_session: Session):
        a = Asset(name="zomb", asset_ip="10.0.0.9")
        active = Asset(name="alive", asset_ip="10.0.0.10")
        db_session.add_all([a, active])
        db_session.commit()

        # active：有行为流量
        db_session.add(BehaviorProfile(
            asset_id=active.id, ip="10.0.0.10",
            profile_date=date.today(), total=50,
        ))
        # zomb：无任何记录
        db_session.commit()

        out = detect_zombies(db_session, days=14)
        ids = {c["asset_id"]: c for c in out["candidates"]}
        assert str(a.id) in ids
        assert str(active.id) not in ids
        assert ids[str(a.id)]["confidence"] == 0.4  # 无画像史

    def test_identity_events_prevent_zombie(self, db_session: Session):
        a = Asset(name="auth-only", asset_ip="10.0.0.11")
        db_session.add(a)
        db_session.commit()
        db_session.add(IdentityEvent(
            es_index="i", es_doc_id="d1", dst_ip="10.0.0.11",
            success=True, event_type="auth_success",
            ts=datetime.utcnow() - timedelta(days=2),
        ))
        db_session.commit()

        out = detect_zombies(db_session, days=14)
        assert str(a.id) not in {c["asset_id"] for c in out["candidates"]}

    def test_zero_traffic_with_history_higher_confidence(self, db_session: Session):
        a = Asset(name="was-active", asset_ip="10.0.0.12")
        db_session.add(a)
        db_session.commit()
        # 历史有快照（窗口外），窗口内零流量
        db_session.add(BehaviorProfile(
            asset_id=a.id, ip="10.0.0.12",
            profile_date=date.today() - timedelta(days=30), total=100,
        ))
        db_session.commit()

        out = detect_zombies(db_session, days=14)
        hit = {c["asset_id"]: c for c in out["candidates"]}.get(str(a.id))
        assert hit and hit["confidence"] == 0.7


class TestZombieClearance:
    def _ticket(self, asset_id: str, status: str):
        from app.models.remediation_ticket import RemediationTicket
        return RemediationTicket(
            source_type="ueba_zombie",
            asset_id=asset_id,
            severity="medium",
            status=status,
            title="zombie",
            created_by="tester",
        )

    def test_empty_rate_is_none(self, db_session: Session):
        out = zombie_clearance_rate(db_session)
        assert out["clearance_rate"] is None
        assert out["dispatched_assets"] == 0

    def test_partial_clearance(self, db_session: Session):
        a1 = Asset(name="z1", asset_ip="10.0.1.9")
        a2 = Asset(name="z2", asset_ip="10.0.1.10")
        a3 = Asset(name="z3", asset_ip="10.0.1.11")
        db_session.add_all([a1, a2, a3])
        db_session.commit()
        db_session.add_all([
            self._ticket(str(a1.id), "verified"),
            self._ticket(str(a2.id), "verified"),
            self._ticket(str(a3.id), "open"),
        ])
        db_session.commit()

        out = zombie_clearance_rate(db_session)
        assert out["dispatched_assets"] == 3
        assert out["cleared_assets"] == 2
        assert out["in_flight_assets"] == 1
        assert out["clearance_rate"] == pytest.approx(2 / 3, abs=1e-4)

    def test_cancelled_not_counted_as_cleared(self, db_session: Session):
        a = Asset(name="zc", asset_ip="10.0.1.12")
        db_session.add(a)
        db_session.commit()
        db_session.add(self._ticket(str(a.id), "cancelled"))
        db_session.commit()

        out = zombie_clearance_rate(db_session)
        assert out["cleared_assets"] == 0
        assert out["cancelled_assets"] == 1
        assert out["clearance_rate"] == 0.0
