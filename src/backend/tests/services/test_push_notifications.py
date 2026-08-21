"""
F4.2 主动推送服务测试

覆盖（PRD F4.2 表 + 频控）：
- 源健康异常：中断超阈值 / expected_interval 双周期 / 从未成功
- 风险突变：7 天 Δ≥20 触发 / 单点跳过 / 低于阈值不触发
- EOL 临近（F3.2 联动）：30 天 info / 7 天 warn / 已超期 warn / 窗口外不推
- 频控去重：窗口内第二轮 0 发送；规则关闭 0 发送
- 规则存取：深合并保存/读取
- 接收人：仅 active 用户
"""
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.models import Asset, Notification
from app.models.asset_risk import AssetRiskHistory
from app.models.source_health import SourceHealth
from app.models.user import User, UserStatus
from app.models.role import Role
from app.core.security import get_password_hash
from app.services.push_notification_service import (
    PushNotificationService, DEFAULT_PUSH_RULES, _rules_cache,
)


def _now():
    return datetime.now(timezone.utc)


def _make_users(db):
    """一个 active + 一个 disabled 用户"""
    role = Role(name="测试", code="test_push", description="")
    db.add(role)
    db.flush()
    u1 = User(username="push_active", password_hash=get_password_hash("x"),
              email="a@t.com", full_name="A", role_id=role.id, status=UserStatus.ACTIVE)
    u2 = User(username="push_disabled", password_hash=get_password_hash("x"),
              email="b@t.com", full_name="B", role_id=role.id, status=UserStatus.DISABLED)
    db.add_all([u1, u2])
    db.commit()
    db.refresh(u1); db.refresh(u2)
    return u1, u2


@pytest.fixture(autouse=True)
def _clear_rules_cache():
    _rules_cache["value"] = None
    _rules_cache["at"] = 0.0
    yield
    _rules_cache["value"] = None
    _rules_cache["at"] = 0.0


def _run(coro):
    return asyncio.run(coro)


class TestSourceHealth:
    def test_down_over_threshold_triggers(self, db_session):
        u1, u2 = _make_users(db_session)
        s = SourceHealth(source_key="loki:xyz", source_type="loki", display_name="Loki XYZ",
                         last_success_at=_now() - timedelta(hours=5), failure_count=3)
        db_session.add(s)
        db_session.commit()
        svc = PushNotificationService(db_session)
        sent = _run(svc.check_source_health())
        assert sent == 1  # 1 个 active 用户
        n = db_session.query(Notification).filter_by(type="push").one()
        assert "Loki XYZ" in n.title
        assert "数据链路异常" in n.title

    def test_expected_interval_double(self, db_session):
        """慢周期源：expected=24h → 阈值取 2×周期=48h（比 3h 更宽松，防噪）；
        快周期源仍受 down_hours=3h 下限约束（30min 中断不报）"""
        _make_users(db_session)
        # 快周期：5min 间隔，中断 30min → 阈值 max(3h,10min)=3h → 不报
        db_session.add(SourceHealth(source_key="os:fast", source_type="opensearch",
                                    last_success_at=_now() - timedelta(minutes=30),
                                    expected_interval_seconds=300))
        # 慢周期：24h 间隔，中断 30h → 阈值 max(3h,48h)=48h → 不报
        db_session.add(SourceHealth(source_key="kev:daily", source_type="http",
                                    last_success_at=_now() - timedelta(hours=30),
                                    expected_interval_seconds=86400))
        # 慢周期：中断 50h > 48h → 报
        db_session.add(SourceHealth(source_key="kev:stuck", source_type="http",
                                    last_success_at=_now() - timedelta(hours=50),
                                    expected_interval_seconds=86400))
        db_session.commit()
        assert _run(PushNotificationService(db_session).check_source_health()) == 1
        n = db_session.query(Notification).filter_by(type="push").one()
        assert "kev:stuck" in n.title or "kev:stuck" in (n.content or "")

    def test_never_succeeded(self, db_session):
        _make_users(db_session)
        s = SourceHealth(source_key="tplink:dev", source_type="tplink_collector",
                         last_success_at=None, failure_count=2)
        db_session.add(s)
        db_session.commit()
        svc = PushNotificationService(db_session)
        assert _run(svc.check_source_health()) == 1

    def test_healthy_source_not_triggered(self, db_session):
        _make_users(db_session)
        db_session.add(SourceHealth(source_key="ok:src", source_type="loki",
                                    last_success_at=_now() - timedelta(minutes=5)))
        db_session.commit()
        assert _run(PushNotificationService(db_session).check_source_health()) == 0


class TestRiskJump:
    def _setup_asset(self, db, scores):
        a = Asset(network_segment="3F", asset_ip="192.168.0.95", asset_status="online",
                  criticality="high", name="jump-target")
        db.add(a)
        db.flush()
        base = _now() - timedelta(days=6)
        for i, s in enumerate(scores):
            db.add(AssetRiskHistory(asset_id=a.id, risk_score=s,
                                    scored_at=base + timedelta(hours=12 * i)))
        a.risk_score = scores[-1]
        db.commit()
        return a

    def test_jump_over_threshold(self, db_session):
        u1, u2 = _make_users(db_session)
        a = self._setup_asset(db_session, [20, 25, 45])  # Δ=25 ≥ 20
        sent = _run(PushNotificationService(db_session).check_risk_jump())
        assert sent == 1
        n = db_session.query(Notification).filter_by(type="push").one()
        assert "风险异动" in n.title and "jump-target" in n.title
        assert f"/assets/detail/{a.id}" == n.link  # link 是导航路径

    def test_single_point_skipped(self, db_session):
        """窗口内只有 1 个历史点 → 无趋势，不推送"""
        _make_users(db_session)
        self._setup_asset(db_session, [80])  # 单点高分不算跳变
        assert _run(PushNotificationService(db_session).check_risk_jump()) == 0

    def test_below_threshold_skipped(self, db_session):
        _make_users(db_session)
        self._setup_asset(db_session, [30, 35, 45])  # Δ=15 < 20
        assert _run(PushNotificationService(db_session).check_risk_jump()) == 0


class TestEolApproaching:
    """场景 3：EOL 临近（PRD F4.2 表：30 天 info / 7 天 warn）"""

    def _asset(self, db, days_offset, source="preset"):
        from datetime import date
        a = Asset(network_segment="3F", asset_ip="192.168.0.96", asset_status="online",
                  name="eol-target", os_name="Windows", os_version="11 Pro",
                  expected_eol=date.today() + timedelta(days=days_offset),
                  expected_eol_source=source)
        db.add(a)
        db.commit()
        return a

    def _spy_severity(self, db, monkeypatch):
        """severity 不落库（仅决定去重窗口/日志/未来通道路由）→ 用 spy 断言映射"""
        captured = {}
        svc = PushNotificationService(db)
        real = svc._push

        async def wrapper(**kw):
            captured.update(kw)
            return await real(**kw)

        monkeypatch.setattr(svc, "_push", wrapper)
        return svc, captured

    def test_info_at_30d(self, db_session, monkeypatch):
        _make_users(db_session)
        a = self._asset(db_session, 25)
        svc, cap = self._spy_severity(db_session, monkeypatch)
        assert _run(svc.check_eol()) == 1
        assert cap["severity"] == "info"
        n = db_session.query(Notification).filter_by(type="push").one()
        assert n.title.startswith("【EOL 提醒】") and "剩 25 天" in n.title
        assert "纳入升级规划" in n.content
        assert f"/assets/detail/{a.id}" == n.link

    def test_warn_at_7d(self, db_session, monkeypatch):
        _make_users(db_session)
        self._asset(db_session, 5)
        svc, cap = self._spy_severity(db_session, monkeypatch)
        assert _run(svc.check_eol()) == 1
        assert cap["severity"] == "warn"
        assert "尽快安排升级" in db_session.query(Notification).filter_by(type="push").one().content

    def test_warn_when_expired(self, db_session, monkeypatch):
        _make_users(db_session)
        self._asset(db_session, -100)
        svc, cap = self._spy_severity(db_session, monkeypatch)
        assert _run(svc.check_eol()) == 1
        assert cap["severity"] == "warn"
        n = db_session.query(Notification).filter_by(type="push").one()
        assert "已超期 100 天" in n.title and "无安全补丁" in n.content

    def test_outside_window_not_pushed(self, db_session):
        _make_users(db_session)
        self._asset(db_session, 200)   # 距 EOL 200 天 → 不打扰
        assert _run(PushNotificationService(db_session).check_eol()) == 0

    def test_manual_source_annotated(self, db_session):
        """人工指定的 EOL 同样提醒，但内容标注口径"""
        _make_users(db_session)
        self._asset(db_session, 3, source="manual")
        assert _run(PushNotificationService(db_session).check_eol()) == 1
        assert "人工指定" in db_session.query(Notification).filter_by(type="push").one().content

    def test_dedup_second_round(self, db_session):
        """回归：dedup_title 必须是 title 的稳定前缀，否则每轮巡检都重复推送"""
        _make_users(db_session)
        self._asset(db_session, 5)
        assert _run(PushNotificationService(db_session).check_eol()) == 1
        assert _run(PushNotificationService(db_session).check_eol()) == 0  # 24h 窗口去重


class TestDedupAndRules:
    def test_second_round_deduped(self, db_session):
        _make_users(db_session)
        db_session.add(SourceHealth(source_key="d:src", source_type="loki",
                                    last_success_at=_now() - timedelta(hours=4)))
        db_session.commit()
        svc = PushNotificationService(db_session)
        assert _run(svc.check_source_health()) == 1
        assert _run(svc.check_source_health()) == 0  # 24h 内去重

    def test_dedup_title_prefix_stable(self, db_session):
        """风险异动 title 带 Δ 数字，但去重按稳定前缀——第二轮不同 Δ 也不重发"""
        _make_users(db_session)
        a = self._setup_asset(db_session, [20, 25, 45])
        svc = PushNotificationService(db_session)
        assert _run(svc.check_risk_jump()) == 1
        # 分数继续涨（Δ 变了），窗口内仍去重
        db_session.add(AssetRiskHistory(asset_id=a.id, risk_score=60, scored_at=_now()))
        a.risk_score = 60
        db_session.commit()
        assert _run(svc.check_risk_jump()) == 0

    def _setup_asset(self, db, scores):
        a = Asset(network_segment="3F", asset_ip="192.168.0.96", asset_status="online",
                  criticality="high", name="dedup-target")
        db.add(a)
        db.flush()
        base = _now() - timedelta(days=6)
        for i, s in enumerate(scores):
            db.add(AssetRiskHistory(asset_id=a.id, risk_score=s,
                                    scored_at=base + timedelta(hours=12 * i)))
        a.risk_score = scores[-1]
        db.commit()
        return a

    def test_scenario_disabled(self, db_session):
        _make_users(db_session)
        db_session.add(SourceHealth(source_key="off:src", source_type="loki",
                                    last_success_at=_now() - timedelta(hours=5)))
        db_session.commit()
        svc = PushNotificationService(db_session)
        svc.save_rules({"source_health": {"enabled": False}})
        assert _run(svc.check_source_health()) == 0
        # 全局关闭
        svc.save_rules({"enabled": False})
        assert _run(svc.check_risk_jump()) == 0

    def test_rules_merge(self, db_session):
        svc = PushNotificationService(db_session)
        merged = svc.save_rules({"risk_jump": {"threshold": 30}})
        assert merged["risk_jump"]["threshold"] == 30
        assert merged["risk_jump"]["window_days"] == DEFAULT_PUSH_RULES["risk_jump"]["window_days"]
        again = svc.load_rules(force=True)
        assert again["risk_jump"]["threshold"] == 30
        assert again["source_health"]["down_hours"] == 3  # 未动的场景保持默认
