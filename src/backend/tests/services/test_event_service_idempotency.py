"""P1-T4：行为事件幂等落库测试

测试 INSERT ... ON CONFLICT DO NOTHING 语义：
- 同窗口重复跑：第二次 created=0，DB 仍只 1 条
- 不同窗口：都能正常插入
- unique 约束确实生效
"""
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.dialects.postgresql import insert as pg_insert

# 使用独立测试库
import os
os.environ.setdefault('TEST_DB_NAME', 'AI-miniSOC-db_test')

from app.core.config import settings
from app.models.base import Base
from app.models.browsing_event import BrowsingEvent


def _get_test_engine():
    """获取测试库 engine，独立于主库。"""
    url = settings.DATABASE_URL.replace(settings.DB_NAME, "AI-miniSOC-db_test")
    return create_engine(url, future=True)


@pytest.fixture(scope="module")
def engine():
    eng = _get_test_engine()
    # 跳过 alembic，直接 create_all（测试用，迁移治理不归这里管）
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    # 测试前清空
    session.query(BrowsingEvent).delete()
    session.commit()
    try:
        yield session
    finally:
        session.query(BrowsingEvent).delete()
        session.commit()
        session.close()


def _finding_dict(ip, domain, start_offset_minutes=0):
    """构造一个幂等测试用的 finding 落库 dict（基于 PG insert。values）"""
    base = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    return dict(
        ip=ip,
        domain=domain,
        apptype="web",
        score=80,
        severity="high",
        rule_hits=[{"rule": "R1", "weight": 80, "detail": "test"}],
        source_count=10,
        window_start=base.replace(minute=start_offset_minutes),
        window_end=base.replace(minute=start_offset_minutes + 10),
        status="new",
    )


def test_on_conflict_do_nothing_first_insert_creates_row(db):
    """第一次插入：返回 rowcount=1。"""
    stmt = pg_insert(BrowsingEvent).values(**_finding_dict("192.168.0.1", "evil.com")).on_conflict_do_nothing(
        index_elements=["ip", "domain", "window_start", "window_end"]
    )
    r = db.execute(stmt)
    db.commit()
    assert r.rowcount == 1
    assert db.query(BrowsingEvent).count() == 1


def test_on_conflict_do_nothing_duplicate_no_new_row(db):
    """同窗口重复：第二次 rowcount=0，DB 仍只 1 条。"""
    payload = _finding_dict("192.168.0.1", "evil.com")
    stmt = (
        pg_insert(BrowsingEvent)
        .values(**payload)
        .on_conflict_do_nothing(index_elements=["ip", "domain", "window_start", "window_end"])
    )
    db.execute(stmt)
    db.commit()

    # 再插一次（完全相同 payload）
    stmt2 = (
        pg_insert(BrowsingEvent)
        .values(**payload)
        .on_conflict_do_nothing(index_elements=["ip", "domain", "window_start", "window_end"])
    )
    r2 = db.execute(stmt2)
    db.commit()
    assert r2.rowcount == 0
    assert db.query(BrowsingEvent).count() == 1


def test_on_conflict_different_window_inserts_new(db):
    """不同窗口（即使 ip/domain 相同）：可以新增。"""
    p1 = _finding_dict("192.168.0.1", "evil.com", start_offset_minutes=0)
    p2 = _finding_dict("192.168.0.1", "evil.com", start_offset_minutes=10)  # 10 分钟错开

    for p in (p1, p2):
        db.execute(
            pg_insert(BrowsingEvent)
            .values(**p)
            .on_conflict_do_nothing(index_elements=["ip", "domain", "window_start", "window_end"])
        )
    db.commit()
    assert db.query(BrowsingEvent).count() == 2


def test_on_conflict_different_ip_inserts_new(db):
    """不同 ip：可以新增（即使窗口相同）。"""
    p1 = _finding_dict("192.168.0.1", "evil.com")
    p2 = _finding_dict("192.168.0.2", "evil.com")
    for p in (p1, p2):
        db.execute(
            pg_insert(BrowsingEvent)
            .values(**p)
            .on_conflict_do_nothing(index_elements=["ip", "domain", "window_start", "window_end"])
        )
    db.commit()
    assert db.query(BrowsingEvent).count() == 2


def test_unique_constraint_active_in_db(engine):
    """DB 侧唯一约束实际生效：直接 INSERT 重复应被 DB 拒绝。"""
    payload = _finding_dict("192.168.0.99", "dup.com")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM soc_browsing_events WHERE ip = '192.168.0.99'"))
        conn.execute(
            pg_insert(BrowsingEvent).values(**payload).on_conflict_do_nothing(
                index_elements=["ip", "domain", "window_start", "window_end"]
            )
        )
    # 第二次直接 INSERT（不走 ON CONFLICT）应失败
    from sqlalchemy.exc import IntegrityError
    try:
        with engine.begin() as conn:
            conn.execute(BrowsingEvent.__table__.insert().values(**payload))
        assert False, "should have raised IntegrityError"
    except IntegrityError:
        pass  # 预期：DB 拒绝重复