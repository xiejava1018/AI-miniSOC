"""P2-T4：同步失败可追踪/重放单测"""
import sys
from pathlib import Path
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.base import Base
from app.models.sync_dead_letter import SyncDeadLetter
from app.services.sync_dead_letter import DeadLetterRecorder, replay_batch


def _get_test_engine():
    url = settings.DATABASE_URL.replace(settings.DB_NAME, "AI-miniSOC-db_test")
    return create_engine(url, future=True)


@pytest.fixture(scope="module")
def engine():
    eng = _get_test_engine()
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    session.query(SyncDeadLetter).delete()
    session.commit()
    try:
        yield session
    finally:
        session.query(SyncDeadLetter).delete()
        session.commit()
        session.close()


def test_record_creates_row(db):
    """record() 入库一行（含 batch_id、错误类型、原文）。"""
    batch_id = uuid.uuid4()
    rec = DeadLetterRecorder(db, batch_id=batch_id)
    rec.record(
        source="test",
        data_type="asset",
        item_index=0,
        raw_item={"asset_ip": "1.2.3.4"},
        error=ValueError("missing field"),
        item_key="1.2.3.4",
    )
    db.commit()
    rows = db.query(SyncDeadLetter).filter_by(batch_id=batch_id).all()
    assert len(rows) == 1
    assert rows[0].error_class == "ValueError"
    assert "missing field" in rows[0].error_message
    assert rows[0].item_key == "1.2.3.4"
    assert rows[0].resolved is False
    assert rows[0].batch_id == batch_id


def test_replay_resolves_records(db):
    """replay_batch：handler 成功调用后，全部 dead_letter 标 resolved，replay_count +1。"""
    batch_id = uuid.uuid4()
    rec = DeadLetterRecorder(db, batch_id=batch_id)
    for i in range(3):
        rec.record(
            source="test", data_type="asset", item_index=i,
            raw_item={"asset_ip": f"1.2.3.{i}"}, error=ValueError("bad"),
        )
    db.commit()

    def fake_handler(source, items, db):
        # 假设第二次重放全部成功
        return {"created": len(items)}

    result = replay_batch(db, batch_id=batch_id, handler_callable=fake_handler)
    assert result["total"] == 3
    assert result["resolved"] == 3
    assert result["still_failing"] == 0

    rows = db.query(SyncDeadLetter).filter_by(batch_id=batch_id).all()
    for r in rows:
        assert r.resolved is True
        assert r.replay_count == 1
        assert r.last_replayed_at is not None


def test_replay_still_failing_increments_count(db):
    """handler 仍失败：replay_count +1，resolved 仍 False。"""
    batch_id = uuid.uuid4()
    rec = DeadLetterRecorder(db, batch_id=batch_id)
    rec.record(
        source="test", data_type="asset", item_index=0,
        raw_item={"asset_ip": "1.1.1.1"}, error=ValueError("bad"),
    )
    db.commit()

    def still_bad_handler(source, items, db):
        raise RuntimeError("still broken")

    result = replay_batch(db, batch_id=batch_id, handler_callable=still_bad_handler)
    assert result["total"] == 1
    assert result["resolved"] == 0
    assert result["still_failing"] == 1

    row = db.query(SyncDeadLetter).filter_by(batch_id=batch_id).first()
    assert row.resolved is False
    assert row.replay_count == 1
    assert row.last_replayed_at is not None


def test_replay_no_unresolved_returns_empty(db):
    """无未解决 dead_letter 时返回空统计，不调 handler。"""
    called = []

    def handler(source, items, db):
        called.append(True)

    result = replay_batch(db, batch_id=uuid.uuid4(), handler_callable=handler)
    assert result == {"total": 0, "resolved": 0, "still_failing": 0}
    assert called == []  # handler 未被调用