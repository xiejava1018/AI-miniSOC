"""
F1.2 安全态势摘要服务测试

覆盖（PRD F1.2 / §八-C / X2）：
- 聚合统计：告警簇优先级分布 + top 规则 + 事件（含未关闭）
- is_noise 过滤（降噪后才进摘要）
- 降级：预算拒绝 → 统计模板文案（含数据窗口口径标注，不编造）
- 空数据：如实说明（禁止编趋势，§八-B）
- 缓存命中 / force 绕过
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Asset, AlertGroupAnalysis
from app.models.incident import Incident
from app.models.asset_incident import AssetIncident
from app.services.asset_security import AssetSecurityService, _summary_cache, _cache_generated


def _now():
    return datetime.now(timezone.utc)


def _make_asset(**kw):
    defaults = dict(
        network_segment="3F", asset_ip="192.168.0.90", asset_status="online",
        asset_type="server", criticality="high", os_name="Ubuntu", os_version="22.04",
        name="sec-test",
    )
    defaults.update(kw)
    return Asset(**defaults)


@pytest.fixture(autouse=True)
def _clear_cache():
    _summary_cache.clear()
    _cache_generated.clear()
    yield
    _summary_cache.clear()
    _cache_generated.clear()


class TestCollectStats:
    def test_aggregation(self, db_session):
        a = _make_asset()
        db_session.add(a)
        db_session.flush()
        for i, (prio, noise) in enumerate([
            ("P1", False), ("P1", False), ("P2", False), ("P3", False), ("P0", True),  # 最后一个是噪声
        ]):
            db_session.add(AlertGroupAnalysis(
                fingerprint=f"sf{i}", priority=prio, is_noise=noise,
                linked_asset_id=a.id, rule_description="SSH brute force attempt",
            ))
        inc1 = Incident(title="SSH爆破事件", status="open", severity="high", created_by="test")
        inc2 = Incident(title="已闭环", status="closed", severity="low", created_by="test")
        db_session.add_all([inc1, inc2])
        db_session.flush()
        db_session.add_all([
            AssetIncident(asset_id=a.id, incident_id=inc1.id),
            AssetIncident(asset_id=a.id, incident_id=inc2.id),
        ])
        a.risk_score = 55
        db_session.commit()

        stats = AssetSecurityService(db_session).collect_stats(a, 30)
        # 噪声簇被过滤：5 个簇只计 4 个
        assert stats["alert_groups"]["total"] == 4
        assert stats["alert_groups"]["by_priority"]["P1"] == 2
        assert stats["alert_groups"]["top_rules"][0]["description"] == "SSH brute force attempt"
        assert stats["alert_groups"]["top_rules"][0]["count"] == 4
        assert stats["incidents"]["total"] == 2
        assert stats["incidents"]["open"] == 1  # closed 不算
        assert stats["risk"]["risk_score"] == 55
        # X2：窗口标注存在
        assert stats["window"]["days"] == 30
        assert stats["window"]["start"] and stats["window"]["end"]

    def test_window_filter(self, db_session):
        """窗口外的告警簇不计入（31 天前）"""
        a = _make_asset()
        db_session.add(a)
        db_session.flush()
        old = AlertGroupAnalysis(fingerprint="old", priority="P0", linked_asset_id=a.id)
        db_session.add(old)
        db_session.flush()
        db_session.query(AlertGroupAnalysis).filter_by(fingerprint="old").update(
            {"created_at": _now() - timedelta(days=31)})
        db_session.commit()
        stats = AssetSecurityService(db_session).collect_stats(a, 30)
        assert stats["alert_groups"]["total"] == 0


class TestSummary:
    def test_fallback_when_budget_rejected(self, db_session, monkeypatch):
        """预算拒绝 → 统计模板，含「统计口径」标注（§八-C 降级）"""
        a = _make_asset()
        db_session.add(a)
        db_session.flush()
        db_session.add(AlertGroupAnalysis(
            fingerprint="s1", priority="P1", linked_asset_id=a.id,
            rule_description="SSHD auth failure",
        ))
        a.risk_score = 42
        db_session.commit()
        monkeypatch.setattr("app.services.asset_security.ai_budget.allow", lambda: False)
        out = AssetSecurityService(db_session).security_summary(a.id)
        assert out["summary_source"] == "rule"
        assert "统计口径生成" in out["summary"]
        assert "SSHD auth failure" in out["summary"]
        assert "42" in out["summary"]

    def test_empty_data_honest(self, db_session, monkeypatch):
        """空数据如实说明，不编造（§八-B）"""
        a = _make_asset()
        db_session.add(a)
        db_session.commit()
        monkeypatch.setattr("app.services.asset_security.ai_budget.allow", lambda: False)
        out = AssetSecurityService(db_session).security_summary(a.id)
        assert "无降噪后告警簇记录" in out["summary"]

    def test_cache_hit_and_force(self, db_session, monkeypatch):
        a = _make_asset()
        db_session.add(a)
        db_session.commit()
        monkeypatch.setattr("app.services.asset_security.ai_budget.allow", lambda: False)
        svc = AssetSecurityService(db_session)
        out1 = svc.security_summary(a.id)
        gen1 = out1["generated_at"]
        out2 = svc.security_summary(a.id)  # 命中缓存
        assert out2["generated_at"] == gen1
        out3 = svc.security_summary(a.id, force=True)  # 绕过
        assert out3["generated_at"] != gen1

    def test_nonexistent_asset(self, db_session):
        import uuid
        assert AssetSecurityService(db_session).security_summary(uuid.uuid4()) is None
