"""EntityResolver 单测（D-2 拍板：G5 优先级链 / G6 覆盖率 / G7 不建表）。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.identity import IdentityEvent
from app.services.entity_resolver import EntityResolver


def _asset(db, ip, agent=None, mac=None, name="a"):
    a = Asset(name=name, asset_ip=ip, wazuh_agent_id=agent, mac_address=mac)
    db.add(a)
    db.flush()
    return a


class TestPriorityChain:
    def test_agent_highest(self, db_session: Session):
        a = _asset(db_session, "10.9.0.1", agent="007", mac="aa:bb:cc:dd:ee:01")
        db_session.commit()
        out = EntityResolver(db_session).resolve("007")
        assert out["asset_id"] == str(a.id)
        assert out["matched_by"] == "wazuh_agent_id"

    def test_ip_fallback(self, db_session: Session):
        a = _asset(db_session, "10.9.0.2", mac="aa:bb:cc:dd:ee:02")
        db_session.commit()
        out = EntityResolver(db_session).resolve("10.9.0.2")
        assert out["asset_id"] == str(a.id)
        assert out["matched_by"] == "asset_ip"

    def test_mac_third(self, db_session: Session):
        a = _asset(db_session, "10.9.0.3", mac="AA:BB:CC:DD:EE:03")
        db_session.commit()
        out = EntityResolver(db_session).resolve("aa:bb:cc:dd:ee:03")
        assert out["asset_id"] == str(a.id)
        assert out["matched_by"] == "mac_address"

    def test_log_ip_private_with_event(self, db_session: Session):
        a = _asset(db_session, "10.9.0.4")
        db_session.commit()
        from datetime import datetime
        db_session.add(IdentityEvent(
            es_index="i", es_doc_id="er1", dst_ip="10.9.0.4",
            success=True, event_type="auth_success",
            ts=datetime.utcnow(),
        ))
        db_session.commit()
        out = EntityResolver(db_session).resolve("10.9.0.4")
        # asset_ip 链先命中（优先级 2 > 4）
        assert out["matched_by"] == "asset_ip"

    def test_external_ip_not_anchored_via_log(self, db_session: Session):
        """G5 拍板：外网攻击 IP 禁锚资产。"""
        _asset(db_session, "10.9.0.5")
        from datetime import datetime
        db_session.add(IdentityEvent(
            es_index="i", es_doc_id="er2", src_ip="45.148.10.155",
            dst_ip="10.9.0.5", success=False, event_type="auth_failed",
            ts=datetime.utcnow(),
        ))
        db_session.commit()
        out = EntityResolver(db_session).resolve("45.148.10.155",
                                                 alias_type="log_ip")
        assert out["asset_id"] is None
        assert "外网 IP" in out["note"]

    def test_no_match(self, db_session: Session):
        out = EntityResolver(db_session).resolve("10.9.9.9")
        assert out["asset_id"] is None

    def test_conflict_no_guess(self, db_session: Session):
        """同级多命中 → None + conflicts（不猜）。"""
        from datetime import datetime, timedelta
        _asset(db_session, "10.9.0.6", name="c1")
        # 唯一约束挡重复 IP —— 用 mac 冲突模拟同级多命中
        db_session.commit()
        # 直接构造：同 mac 两个资产
        a1 = Asset(name="m1", asset_ip="10.9.1.1", mac_address="aa:bb:cc:dd:ee:f1")
        a2 = Asset(name="m2", asset_ip="10.9.1.2", mac_address="aa:bb:cc:dd:ee:f1")
        db_session.add_all([a1, a2])
        db_session.commit()
        out = EntityResolver(db_session).resolve("aa:bb:cc:dd:ee:f1")
        assert out["asset_id"] is None
        assert len(out["conflicts"]) == 2
        assert "拒绝猜测" in out["note"]


class TestExplicitType:
    def test_agent_only(self, db_session: Session):
        a = _asset(db_session, "10.9.2.1", agent="042")
        db_session.commit()
        out = EntityResolver(db_session).resolve(
            "042", alias_type="wazuh_agent_id")
        assert out["asset_id"] == str(a.id)


class TestRegisterAlias:
    def test_not_supported(self, db_session: Session):
        out = EntityResolver(db_session).register_alias("x", "ip", "1.2.3.4")
        assert out["supported"] is False
        assert "G7" in out["reason"] or "不建" in out["reason"]


class TestCoverage:
    def test_segments(self, db_session: Session):
        _asset(db_session, "10.9.3.1", agent="001")
        _asset(db_session, "10.9.3.2")
        db_session.commit()
        cov = EntityResolver(db_session).coverage()
        assert cov["assets_total"] >= 2
        assert cov["by_indicator"]["asset_ip"]["covered"] >= 2
        assert cov["by_indicator"]["wazuh_agent_id"]["covered"] >= 1
        assert "口径" in cov["note"] or "分母" in cov["note"]


class TestBatch:
    def test_batch(self, db_session: Session):
        a = _asset(db_session, "10.9.4.1", agent="009")
        db_session.commit()
        out = EntityResolver(db_session).resolve_batch(["009", "10.9.4.99"])
        assert out["total"] == 2
        assert out["hit"] == 1
