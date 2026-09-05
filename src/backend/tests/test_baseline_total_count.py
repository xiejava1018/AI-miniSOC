"""BaselineService.upsert_many total_count 口径修复验证（2026-09-05 止血）。

原缺陷：同 (ip, domain) 记录在 upsert 前被 dict 去重，每键只 +1，
累计的是"检测轮次数"而非真实访问次数。修复后应累加真实次数。
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.models.browsing_baseline import BrowsingBaseline
from app.services.browsing_detection.baseline_service import BaselineService
from app.services.browsing_detection.log_parser import BrowsingRecord


def _rec(ip, domain, offset_min):
    return BrowsingRecord(
        ip=ip, domain=domain, action="url",
        ts=datetime.now(timezone.utc) + timedelta(minutes=offset_min),
    )


@pytest.fixture()
def _clean_baseline(db_session):
    db_session.query(BrowsingBaseline).filter(
        BrowsingBaseline.ip == "192.168.99.99"
    ).delete()
    db_session.commit()
    yield
    db_session.query(BrowsingBaseline).filter(
        BrowsingBaseline.ip == "192.168.99.99"
    ).delete()
    db_session.commit()


def _get_count(db, ip, domain):
    row = (
        db.query(BrowsingBaseline)
        .filter(BrowsingBaseline.ip == ip, BrowsingBaseline.domain == domain)
        .first()
    )
    return row.total_count if row else None


def test_insert_counts_real_visits(db_session, _clean_baseline):
    """首轮：3 条同键记录应写入 total_count=3（而非 1）"""
    recs = [_rec("192.168.99.99", "example.com", i) for i in range(3)]
    assert BaselineService(db_session).upsert_many(recs) == 1
    assert _get_count(db_session, "192.168.99.99", "example.com") == 3


def test_conflict_accumulates_real_visits(db_session, _clean_baseline):
    """第二轮冲突 upsert：应累加本轮真实次数（3+2=5，而非 3+1=4）"""
    svc = BaselineService(db_session)
    svc.upsert_many([_rec("192.168.99.99", "example.com", i) for i in range(3)])
    svc.upsert_many([_rec("192.168.99.99", "example.com", i) for i in range(2)])
    assert _get_count(db_session, "192.168.99.99", "example.com") == 5


def test_multi_key_grouping(db_session, _clean_baseline):
    """多键混合：各键独立计数，外部/无域名记录被跳过"""
    recs = [
        _rec("192.168.99.99", "a.com", 0),
        _rec("192.168.99.99", "a.com", 1),
        _rec("192.168.99.99", "b.com", 0),
        _rec("8.8.8.8", "c.com", 0),        # 外网跳过
        _rec("192.168.99.99", "", 0),        # 无域名跳过
    ]
    assert BaselineService(db_session).upsert_many(recs) == 2
    assert _get_count(db_session, "192.168.99.99", "a.com") == 2
    assert _get_count(db_session, "192.168.99.99", "b.com") == 1
