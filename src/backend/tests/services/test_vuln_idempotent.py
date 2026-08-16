"""P2-T5：OS 同步写入幂等测试"""
import sys
from pathlib import Path
import uuid
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.base import Base
from app.models.vulnerability import Vulnerability, AssetVulnerability
from app.models.asset import Asset
from app.services.vuln_idempotent import upsert_vulnerability, upsert_asset_vulnerability


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
    # 测试前清相关表
    session.query(AssetVulnerability).delete()
    session.query(Vulnerability).delete()
    session.query(Asset).delete()
    session.commit()
    try:
        yield session
    finally:
        session.query(AssetVulnerability).delete()
        session.query(Vulnerability).delete()
        session.query(Asset).delete()
        session.commit()
        session.close()


def _make_asset(db) -> Asset:
    a = Asset(
        network_segment="default",
        asset_ip="192.168.0.99",
        asset_description="Test asset",
        asset_status="up",
    )
    db.add(a)
    db.flush()
    return a


def test_upsert_vulnerability_first_insert(db):
    """首次插入 vulns：返回 1 行。"""
    v = upsert_vulnerability(
        db,
        cve_id="CVE-2026-0001",
        title="Test 1",
        severity="high",
        cvss_score=7.5,
    )
    db.commit()
    assert db.query(Vulnerability).count() == 1
    assert v.cve_id == "CVE-2026-0001"


def test_upsert_vulnerability_idempotent_no_growth(db):
    """重跑同 cve：行数不增长。"""
    upsert_vulnerability(db, cve_id="CVE-2026-0002", title="t", severity="medium")
    db.commit()
    upsert_vulnerability(db, cve_id="CVE-2026-0002", title="t", severity="medium")
    upsert_vulnerability(db, cve_id="CVE-2026-0002", title="t", severity="medium")
    db.commit()
    assert db.query(Vulnerability).count() == 1


def test_upsert_vulnerability_updates_fields(db):
    """重跑：更新字段（severity 变化）。"""
    upsert_vulnerability(db, cve_id="CVE-2026-0003", title="orig", severity="low")
    db.commit()
    upsert_vulnerability(db, cve_id="CVE-2026-0003", title="updated", severity="high")
    db.commit()
    rows = db.query(Vulnerability).filter_by(cve_id="CVE-2026-0003").all()
    assert len(rows) == 1
    assert rows[0].title == "updated"
    assert rows[0].severity == "high"


def test_upsert_asset_vulnerability_idempotent(db):
    """重跑同 (asset,vuln,scanner)：行数不增长。"""
    asset = _make_asset(db)
    v = upsert_vulnerability(db, cve_id="CVE-2026-0004", title="t", severity="low")
    db.flush()

    upsert_asset_vulnerability(db, asset_id=asset.id, vulnerability_id=v.id, scanner="wazuh")
    upsert_asset_vulnerability(db, asset_id=asset.id, vulnerability_id=v.id, scanner="wazuh")
    db.commit()

    assert db.query(AssetVulnerability).count() == 1


def test_upsert_asset_vulnerability_different_scanner_inserts(db):
    """不同 scanner：(asset,vuln,scanner) 不同 → 新增。"""
    asset = _make_asset(db)
    v = upsert_vulnerability(db, cve_id="CVE-2026-0005", title="t", severity="low")
    db.flush()

    upsert_asset_vulnerability(db, asset_id=asset.id, vulnerability_id=v.id, scanner="wazuh")
    upsert_asset_vulnerability(db, asset_id=asset.id, vulnerability_id=v.id, scanner="manual")
    db.commit()

    assert db.query(AssetVulnerability).count() == 2


def test_unique_constraints_active_in_db(engine):
    """DB 侧唯一约束生效：直接 INSERT 重复 cve 应被拒绝。"""
    from sqlalchemy.exc import IntegrityError
    with engine.begin() as conn:
        conn.execute(
            Vulnerability.__table__.insert().values(
                cve_id="CVE-2026-0099",
                title="direct insert",
                severity="low",
            )
        )
    try:
        with engine.begin() as conn:
            conn.execute(
                Vulnerability.__table__.insert().values(
                    cve_id="CVE-2026-0099",  # 同 cve
                    title="dup",
                    severity="low",
                )
            )
        assert False, "should have raised IntegrityError"
    except IntegrityError:
        pass  # 预期：DB 拒绝