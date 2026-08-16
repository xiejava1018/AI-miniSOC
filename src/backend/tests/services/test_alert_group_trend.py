"""
测试告警簇快照趋势聚合（get_trend 口径修复回归）

背景（2026-08-16）：get_trend 曾用 count(*) 数每日"簇数"，但一天内调度器
可能跑多次快照，同一指纹会写多行 —— 行数被当成簇数（8/15 快照跑 23 次，
行数 696 被当成"簇数"，真实簇数仅 35）。修复后：
- clusters      = 每日 distinct fingerprint
- alerts        = 每指纹取当日 count 最大值再求和（不跨快照重复累加）
- linked_assets = 每日 distinct linked_asset_id
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.models.alert_group_snapshot import AlertGroupSnapshot
from app.models.asset import Asset
from app.services.alert_group_snapshot_service import AlertGroupSnapshotService

DAY = datetime(2026, 8, 15, 2, 0, tzinfo=timezone.utc)  # 当天 10:00 北京时间，留足同日余量
ASSET_A = uuid.uuid4()
ASSET_B = uuid.uuid4()


def _seed_assets(db_session):
    """linked_asset_id 有外键约束，需先插资产行。"""
    db_session.add_all([
        Asset(id=ASSET_A, name="host-a", asset_ip="192.168.0.10"),
        Asset(id=ASSET_B, name="host-b", asset_ip="192.168.0.11"),
    ])
    db_session.flush()


def _snap(fingerprint: str, count: int, asset_id=None, at=DAY):
    return AlertGroupSnapshot(
        snapshot_at=at,
        window_hours=24,
        fingerprint=fingerprint,
        rule_id="100",
        rule_description="test rule",
        agent_id="001",
        agent_name="host-a",
        agent_ip="192.168.0.10",
        count=count,
        level_min=3,
        level_max=7,
        linked_asset_id=asset_id,
    )


def test_trend_dedupes_multi_snapshot_days(db_session):
    """同一天跑 3 次快照：2 个指纹（fp-1 关联资产A，fp-2 关联资产B）。

    修复前 count(*) = 6（3 快照 × 2 簇），sum(count) = 60；
    修复后 clusters = 2，alerts = 5+30 = 35（每指纹取 max），linked = 2。
    """
    _seed_assets(db_session)
    rows = (
        # 第一次快照
        _snap("fp-1", 3, ASSET_A, at=DAY),
        _snap("fp-2", 20, ASSET_B, at=DAY),
        # 第二次快照（fp-1 窗口告警量涨到 5）
        _snap("fp-1", 5, ASSET_A, at=DAY + timedelta(hours=6)),
        _snap("fp-2", 30, ASSET_B, at=DAY + timedelta(hours=6)),
        # 第三次快照（count 回落，max 语义应取历史最大窗口）
        _snap("fp-1", 4, ASSET_A, at=DAY + timedelta(hours=12)),
        _snap("fp-2", 10, ASSET_B, at=DAY + timedelta(hours=12)),
    )
    db_session.add_all(rows)
    db_session.commit()

    result = AlertGroupSnapshotService(db_session).get_trend(days=14)
    assert len(result["days"]) == 1
    d = result["days"][0]
    assert d["clusters"] == 2, "同日多次快照应按 distinct fingerprint 去重"
    assert d["alerts"] == 35, "每指纹应取当日 max(count) 再求和，不跨快照累加"
    assert d["linked_assets"] == 2, "应数 distinct 资产数而非有资产关联的指纹数"


def test_trend_separates_days_and_ignores_null_asset(db_session):
    """两天各 1 指纹，其中一天关联为 NULL —— linked 不应计 NULL。"""
    _seed_assets(db_session)
    db_session.add_all([
        _snap("fp-1", 10, ASSET_A, at=DAY),
        _snap("fp-2", 10, None, at=DAY + timedelta(days=1)),  # 未关联资产
    ])
    db_session.commit()

    result = AlertGroupSnapshotService(db_session).get_trend(days=14)
    by_date = {d["date"]: d for d in result["days"]}
    assert by_date["2026-08-15"]["linked_assets"] == 1
    assert by_date["2026-08-16"]["linked_assets"] == 0, "NULL linked_asset_id 不应计入"


def test_trend_excludes_rows_outside_window(db_session):
    """窗口外的旧快照不应出现在趋势里。"""
    _seed_assets(db_session)
    db_session.add_all([
        _snap("fp-old", 99, ASSET_A, at=datetime.now(timezone.utc) - timedelta(days=30)),
        _snap("fp-new", 5, ASSET_A),
    ])
    db_session.commit()

    result = AlertGroupSnapshotService(db_session).get_trend(days=14)
    dates = [d["date"] for d in result["days"]]
    assert len(dates) == 1 and "fp-old" not in dates
