"""P2-T3：数据源健康监控单测"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.base import Base
from app.models.source_health import SourceHealth
from app.services.source_health import SourceHealthRecorder, is_healthy, utc_now


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
    session.query(SourceHealth).delete()
    session.commit()
    try:
        yield session
    finally:
        session.query(SourceHealth).delete()
        session.commit()
        session.close()


def test_record_success_creates_new_row(db):
    """首次 success：INSERT 一行。"""
    recorder = SourceHealthRecorder(db)
    recorder.record_success(
        "loki:test",
        source_type="loki",
        records_count=100,
        expected_interval_seconds=300,
    )
    db.commit()
    row = db.get(SourceHealth, "loki:test")
    assert row is not None
    assert row.source_type == "loki"
    assert row.success_count == 1
    assert row.last_records_count == 100
    assert row.last_failure_message is None


def test_record_success_updates_existing(db):
    """已有行：success_count +1，更新 last_success_at。"""
    recorder = SourceHealthRecorder(db)
    recorder.record_success("loki:test", source_type="loki", records_count=10)
    db.commit()
    recorder.record_success("loki:test", source_type="loki", records_count=20)
    db.commit()
    row = db.get(SourceHealth, "loki:test")
    assert row.success_count == 2
    assert row.last_records_count == 20


def test_record_failure_increments_failure_count(db):
    """失败计数累加，last_failure_message 写入。"""
    recorder = SourceHealthRecorder(db)
    recorder.record_success("loki:test", source_type="loki")
    db.commit()
    recorder.record_failure("loki:test", source_type="loki", error="connection timeout")
    db.commit()
    row = db.get(SourceHealth, "loki:test")
    assert row.failure_count == 1
    assert "timeout" in (row.last_failure_message or "")


def test_record_success_clears_last_failure_message(db):
    """成功后清空旧错误消息。"""
    recorder = SourceHealthRecorder(db)
    recorder.record_failure("loki:test", source_type="loki", error="boom")
    db.commit()
    recorder.record_success("loki:test", source_type="loki")
    db.commit()
    row = db.get(SourceHealth, "loki:test")
    assert row.last_failure_message is None
    assert row.failure_count == 1  # 失败计数保留


def test_is_healthy_recent_success():
    """最近成功：is_healthy=True。"""
    last = utc_now() - timedelta(seconds=10)
    assert is_healthy(last, expected_interval_seconds=300) is True


def test_is_healthy_stale_source():
    """超 2× 周期：is_healthy=False（标红中断）。"""
    last = utc_now() - timedelta(seconds=700)  # 700s > 2×300s
    assert is_healthy(last, expected_interval_seconds=300) is False


def test_is_healthy_none():
    """无成功记录：False。"""
    assert is_healthy(None, expected_interval_seconds=300) is False