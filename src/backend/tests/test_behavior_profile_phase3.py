"""Phase 3：画像 AI 解读（降级）+ F4.2 场景 8 推送测试"""

import datetime as dt

import pytest

from app.models.behavior_profile import BehaviorProfile
from app.services.behavior_profile.ai_summary import ProfileAIService, _build_facts


# ── ai_summary 降级模板 ──────────────────────────────────

def _profile(total=3000, confidence=90, traffic="human", gap=0, tags=None):
    days = []
    for i in range(gap):
        days.append({"profile_date": f"2026-09-0{i + 1}", "status": "gap",
                     "hostname": "dev", "total": 0})
    days.append({"profile_date": "2026-09-05", "status": "ok", "hostname": "dev",
                 "total": total})
    return {
        "ip": "192.168.0.8", "days": 7, "total": total,
        "daily": days, "gap_days": gap,
        "traffic_type": traffic, "confidence": confidence,
        "asset": {"name": "dev", "asset_type": "client", "owner": None},
        "by_hour": [0] * 6 + [10] * 12 + [30] * 6,
        "layer_visit": {"ACT": 70, "SYS": 25, "AD": 5},
        "cat_share": {"AI 工具": 40.0, "开发技术": 30.0},
        "top_domains": [{"domain": "copilot.tencent.com", "visits": 500, "share": 16.6}],
        "tags": tags or [{"name": "夜猫子", "evidence": "深夜占比 21%"}],
    }


def test_template_summary_ok():
    out = ProfileAIService._template_summary(_build_facts(_profile()))
    assert "数据可信度降级" not in out["summary"]
    assert "3000" in out["summary"].replace(",", "") or "3,000" in out["summary"]
    assert "人工复核" in out["anomaly_interpretation"]


def test_template_summary_degraded():
    out = ProfileAIService._template_summary(_build_facts(_profile(gap=3, confidence=30)))
    assert out["summary"].startswith("数据可信度降级")
    assert "快照缺失" in out["summary"]


def test_template_summary_machine():
    out = ProfileAIService._template_summary(_build_facts(_profile(traffic="machine")))
    assert "机器流量" in out["summary"]


def test_build_facts_field_names_are_self_descriptive():
    """F2.1 教训：事实字段名必须自成量纲"""
    facts = _build_facts(_profile())
    for key in ("total_visits", "window_days", "night_00_06_ratio_pct", "snapshots_ok"):
        assert key in facts


def test_summarize_without_glm_key_uses_template(monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "GLM_API_KEY", None, raising=False)
    out = ProfileAIService().summarize(_profile())
    assert out["source"] == "template"
    assert out["prompt_version"] == "behavior-profile-v1"
    assert "人工复核" in out["disclaimer"]


def test_parse_json_flattens_nested_dict():
    """GLM 返回嵌套 dict 时扁平为文本而非 str(dict)（F3.1 教训）"""
    out = ProfileAIService._parse_json(
        '{"summary": {"a": 1}, "anomaly_interpretation": "x", "recommendations": ["- do", "- check"]}'
    )
    assert out["summary"].startswith("- a:")
    assert "- do" in out["recommendations"]


# ── F4.2 场景 8 推送 ─────────────────────────────────────

def _mk(ip, date, total, by_hour):
    return BehaviorProfile(asset_id=None, ip=ip, profile_date=date, status="ok",
                           total=total, by_hour=by_hour,
                           wd_hour=[[0] * 24 for _ in range(7)], by_block={},
                           confidence=80, traffic_type="human")


@pytest.fixture()
def _jump(db_session):
    """基线 4 天各 1000 次，最新一天 8000 次（8 倍激增）"""
    day = dt.date(2026, 9, 1)
    for i in range(4):
        db_session.add(_mk("192.168.88.8", day + dt.timedelta(days=i), 1000, [0] * 24))
    db_session.add(_mk("192.168.88.8", day + dt.timedelta(days=4), 8000, [0] * 24))
    db_session.commit()
    yield
    db_session.query(BehaviorProfile).filter(BehaviorProfile.ip == "192.168.88.8").delete()
    db_session.commit()


@pytest.mark.anyio
async def test_check_behavior_anomaly_jump(client, db_session, admin_user, _jump):
    from app.services.push_notification_service import PushNotificationService

    svc = PushNotificationService(db_session)
    sent = await svc.check_behavior_anomaly()
    assert sent >= 1
    # dedup：再跑一次不重复推
    assert await svc.check_behavior_anomaly() == 0


@pytest.mark.anyio
async def test_check_behavior_anomaly_skips_small_sample(client, db_session, admin_user):
    """总量 < min_total 的激增是噪音，不推送"""
    from app.services.push_notification_service import PushNotificationService

    day = dt.date(2026, 9, 1)
    for i in range(4):
        db_session.add(_mk("192.168.88.9", day + dt.timedelta(days=i), 10, [0] * 24))
    db_session.add(_mk("192.168.88.9", day + dt.timedelta(days=4), 100, [0] * 24))
    db_session.commit()
    try:
        svc = PushNotificationService(db_session)
        assert await svc.check_behavior_anomaly() == 0
    finally:
        db_session.query(BehaviorProfile).filter(BehaviorProfile.ip == "192.168.88.9").delete()
        db_session.commit()
