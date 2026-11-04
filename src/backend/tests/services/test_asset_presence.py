"""P1/P2/P3 资产存在性（asset_presence）单元测试

覆盖三条公理：
  1. 观测刷新 last_seen / 复活 lifecycle
  2. 覆盖凭证结算：窗口内被看到→清零；缺席→miss_streak 递增→unverified→presumed_offline
  3. retired 终态不被机器改动
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.asset import Asset
from app.models.asset_presence import AssetObservation, ScanCoverage
from app.services.asset_presence import (
    record_observation,
    record_task_coverage,
    settle_coverage,
    STATE_ACTIVE,
    STATE_UNVERIFIED,
    STATE_PRESUMED_OFFLINE,
    STATE_RETIRED,
)


def _mk_asset(db, ip="192.168.0.37", **kw):
    a = Asset(asset_ip=ip, network_segment="test", name="t", **kw)
    db.add(a)
    db.flush()
    return a


def _mk_task(task_uuid, status="success", mode="internal", scope="scheduled"):
    class _T:  # 轻量 duck-typing，record_task_coverage 只读这些属性
        pass
    t = _T()
    t.task_uuid = task_uuid
    t.mode = mode
    t.scope = scope
    t.status = status
    t.items_scanned = 26
    t.finished_at = datetime.now(timezone.utc)
    t.target_summary = [{"type": "cidr", "value": "192.168.0.0/24", "source": "test"}]
    return t


def test_record_observation_revives(db_session):
    a = _mk_asset(db_session, lifecycle_state=STATE_UNVERIFIED, miss_streak=3)
    record_observation(db_session, a.id, "scanner", "active_scan")
    db_session.commit()
    db_session.refresh(a)
    assert a.lifecycle_state == STATE_ACTIVE
    assert a.miss_streak == 0
    assert a.last_seen_at is not None
    obs = db_session.query(AssetObservation).filter_by(asset_id=a.id).all()
    assert len(obs) == 1
    # 幂等心跳合并：同源第二次不新增行
    record_observation(db_session, a.id, "scanner", "active_scan")
    db_session.commit()
    assert db_session.query(AssetObservation).filter_by(asset_id=a.id).count() == 1


def test_record_observation_keeps_retired(db_session):
    a = _mk_asset(db_session, lifecycle_state=STATE_RETIRED)
    record_observation(db_session, a.id, "scanner", "active_scan")
    db_session.commit()
    db_session.refresh(a)
    assert a.lifecycle_state == STATE_RETIRED


def test_coverage_and_settle_marks_missing(db_session, monkeypatch):
    import app.services.asset_presence as ap

    # 绕过 SETTLE_DELAY：结算历史时间戳的凭证
    monkeypatch.setattr(ap, "_scanner_channel_healthy", lambda db: True)
    monkeypatch.setattr(ap, "SETTLE_DELAY_SECONDS", 0)
    monkeypatch.setattr(ap, "get_thresholds", lambda db: {
        "miss_streak_threshold": 2, "offline_days": 30, "fail_alert_threshold": 3,
    })

    gone = _mk_asset(db_session, ip="192.168.0.37")           # 从未被扫到
    alive = _mk_asset(db_session, ip="192.168.0.102")
    retired = _mk_asset(db_session, ip="192.168.0.99", lifecycle_state=STATE_RETIRED)
    outside = _mk_asset(db_session, ip="10.1.1.1")            # 网段外，不该被动
    record_observation(db_session, alive.id, "scanner", "active_scan")
    db_session.commit()

    t = _mk_task("11111111-1111-1111-1111-111111111111")
    record_task_coverage(db_session, t)
    db_session.commit()

    stats = settle_coverage(db_session)
    assert stats["settled"] == 1

    db_session.refresh(gone); db_session.refresh(alive)
    db_session.refresh(retired); db_session.refresh(outside)
    assert gone.miss_streak == 1
    assert gone.lifecycle_state == STATE_ACTIVE          # 1 次缺席还不到阈值
    assert alive.miss_streak == 0
    assert retired.miss_streak == 0                      # 终态不参与
    assert outside.miss_streak == 0                      # 覆盖范围外不动

    # 第二轮覆盖（新 task）→ 达到阈值 → unverified
    t2 = _mk_task("22222222-2222-2222-2222-222222222222")
    record_task_coverage(db_session, t2)
    db_session.commit()
    settle_coverage(db_session)
    db_session.refresh(gone)
    assert gone.miss_streak == 2
    assert gone.lifecycle_state == STATE_UNVERIFIED

    # 幂等：同一凭证重复结算不重复计次
    settle_coverage(db_session)
    db_session.refresh(gone)
    assert gone.miss_streak == 2


def test_settle_promotes_presumed_offline(db_session, monkeypatch):
    import app.services.asset_presence as ap

    monkeypatch.setattr(ap, "_scanner_channel_healthy", lambda db: True)
    monkeypatch.setattr(ap, "SETTLE_DELAY_SECONDS", 0)
    monkeypatch.setattr(ap, "get_thresholds", lambda db: {
        "miss_streak_threshold": 2, "offline_days": 30, "fail_alert_threshold": 3,
    })

    old = datetime.now(timezone.utc) - timedelta(days=60)
    gone = _mk_asset(db_session, ip="192.168.0.37", last_seen_at=old)
    db_session.commit()

    t = _mk_task("33333333-3333-3333-3333-333333333333")
    record_task_coverage(db_session, t)
    db_session.commit()
    settle_coverage(db_session)
    db_session.refresh(gone)
    assert gone.lifecycle_state == STATE_PRESUMED_OFFLINE


def test_failed_coverage_not_settled(db_session):
    # 失败凭证：落库但不参与缺席结算（公理 2：失败≠缺席）
    t = _mk_task("44444444-4444-4444-4444-444444444444", status="failed")
    record_task_coverage(db_session, t)
    db_session.commit()
    cov = db_session.query(ScanCoverage).one()
    assert cov.status == "failed"
    stats = settle_coverage(db_session)
    assert stats["settled"] == 0
