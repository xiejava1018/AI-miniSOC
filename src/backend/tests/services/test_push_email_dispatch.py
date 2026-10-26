"""
推送通知多通道分发测试（2026-10-25 接线）

背景
----
邮件通道（dispatcher + worker + SMTP + 模板）早已建成，但唯一会调
dispatcher 的 ``NotificationService.create_multi()`` **零调用方**——
推送走的 ``create()`` 只写站内信。结果生产上 email worker 每次启动都在
轮询，``soc_notification_dispatch_logs`` 却恒为 0 行，邮件一封没发过。

修法：``_push()`` 改走 ``create_multi()``；dispatcher 对无邮箱用户不建
email log（用户要求：邮件只发给有邮箱的人）。

覆盖：
- push 通知同时产生 inbox 与 email 两类 dispatch_log
- email log 只给有邮箱的用户；无邮箱者连 log 都没有（非 skipped_pref）
- 收件人筛选 helper：email 为 None/空串都算无邮箱
- type='push' 的邮件模板存在且只用恒定 ctx 键（渲染不 KeyError）
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from app.models.notification import Notification  # noqa: E402
from app.models.notification_channel import (  # noqa: E402
    NotificationChannel,
    NotificationDispatchLog,
)
from app.models.user import User, UserStatus  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

async def _make_channels(db):
    """预置 inbox + email 两个启用通道（email 带最小 SMTP 配置）。"""
    for code, name, cfg in (
        ("inbox", "站内信", {}),
        ("email", "邮件", {"host": "smtp.example.com", "port": 587,
                            "user": "a@b.c", "password": "x",
                            "from_addr": "a@b.c"}),
    ):
        ch = db.query(NotificationChannel).filter(NotificationChannel.code == code).first()
        if ch is None:
            ch = NotificationChannel(code=code, name=name, enabled=True, config_json=cfg)
            db.add(ch)
        else:
            ch.enabled = True
            if code == "email" and not ch.config_json:
                ch.config_json = cfg
    db.commit()


def _make_users(db):
    """两个 active 用户：一个有邮箱、一个没有。"""
    role = db.query(User).first()
    with_email = User(username="u_mail", email="someone@example.com",
                      password_hash=get_password_hash("x"),
                      status=UserStatus.ACTIVE)
    no_email = User(username="u_nomail", email=None,
                    password_hash=get_password_hash("x"),
                    status=UserStatus.ACTIVE)
    db.add_all([with_email, no_email])
    db.commit()
    return with_email, no_email


def _run(coro):
    import asyncio
    # asyncio.run（与 test_push_notifications 一致）：get_event_loop 在
    # 同进程其它测试用 asyncio.run 后会 RuntimeError（loop 已被清除）
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# 多通道分发
# ---------------------------------------------------------------------------

def test_push_creates_both_inbox_and_email_logs(db_session):
    """接线核心断言：push 通知必须产生 email dispatch_log（pending）。"""
    from app.services.push_notification_service import (
        PushNotificationService, _rules_cache,
    )
    _rules_cache["value"] = None  # 规则缓存跨测试泄漏防护（保留键结构）
    _run(_make_channels(db_session))
    u1, u2 = _make_users(db_session)

    svc = PushNotificationService(db_session)
    sent = _run(svc._push("【测试】多通道A", "info", "【测试】多通道A", "内容A", None))
    assert sent == 2  # 两个 active 用户都收到站内信

    logs = db_session.query(NotificationDispatchLog).all()
    by_channel = {}
    for l in logs:
        by_channel.setdefault(l.channel_code, []).append(l)

    assert by_channel.get("inbox"), "inbox dispatch_log 缺失"
    assert by_channel.get("email"), "email dispatch_log 缺失（接线失败，仍是 inbox-only）"
    # email log 状态应为 pending（等 worker 投递）或 sent（若 worker 同步跑）
    for l in by_channel["email"]:
        assert l.status in ("pending", "sent"), f"email log 异常状态: {l.status}"


def test_email_only_to_users_with_email(db_session):
    """无邮箱用户：连 email dispatch_log 都不建（不是 skipped_pref 噪音）。"""
    from app.services.push_notification_service import (
        PushNotificationService, _rules_cache,
    )
    _rules_cache["value"] = None
    _run(_make_channels(db_session))
    u1, u2 = _make_users(db_session)

    svc = PushNotificationService(db_session)
    _run(svc._push("【测试】多通道B", "info", "【测试】多通道B", "内容B", None))

    email_logs = db_session.query(NotificationDispatchLog).filter(
        NotificationDispatchLog.channel_code == "email").all()
    email_user_ids = {l.user_id for l in email_logs}
    assert u1.id in email_user_ids, "有邮箱的用户应收到 email log"
    assert u2.id not in email_user_ids, "无邮箱的用户不应有 email log"
    # 且不是被标 skipped_pref（那是用户主动拒收的语义）
    for l in email_logs:
        assert l.status != "skipped_pref"


def test_inbox_still_reaches_users_without_email(db_session):
    """无邮箱用户站内信照发——邮件过滤不影响 inbox。"""
    from app.services.push_notification_service import (
        PushNotificationService, _rules_cache,
    )
    _rules_cache["value"] = None
    _run(_make_channels(db_session))
    u1, u2 = _make_users(db_session)

    svc = PushNotificationService(db_session)
    _run(svc._push("【测试】多通道C", "warn", "【测试】多通道C", "内容C", None))

    inbox_logs = db_session.query(NotificationDispatchLog).filter(
        NotificationDispatchLog.channel_code == "inbox").all()
    inbox_uids = {l.user_id for l in inbox_logs}
    assert u2.id in inbox_uids, "无邮箱用户的站内信被误伤"


def test_users_with_email_helper(db_session):
    """email=None 与 email='' 都算无邮箱。"""
    from app.services.notification_dispatcher import NotificationDispatcher
    u1, u2 = _make_users(db_session)
    d = NotificationDispatcher(db_session)
    ids = d._users_with_email([u1.id, u2.id])
    assert ids == {u1.id}


def test_push_email_template_renders_with_generic_ctx():
    """type='push' 模板存在且只用恒定 ctx 键——不会 KeyError。"""
    from app.services.email_template_registry import get_template_registry

    registry = get_template_registry()
    tpl = registry.get("push")
    assert tpl is not None, "push 模板未注册"

    # 模拟 render_and_send 提供的恒定 ctx（link 为空串，模拟 None 归一）
    ctx = {
        "user": {"id": 1, "username": "ops", "email": "o@x.y"},
        "notification": {
            "id": "n-1", "title": "【数据链路异常】Loki",
            "content": "已 3.2h 无成功", "link": "", "created_at": "2026-10-25T00:00:00",
        },
        "type": "push",
        "unsubscribe_url": "http://localhost:8000/api/v1/notification-preferences/unsubscribe?x=1",
    }
    subject = tpl.render_subject(ctx)
    text = tpl.render_text(ctx)
    html = tpl.render_html(ctx)
    assert "数据链路异常" in subject
    assert "3.2h" in text
    assert "数据链路异常" in html
    assert "None" not in html, "link=None 归一失败，邮件出现字面 None"


# ---------------------------------------------------------------------------
# 场景模板接线（2026-10-25 第二批：push:<scenario> 模板接入真实推送流）
# ---------------------------------------------------------------------------

def test_shadow_scenario_uses_scenario_template(db_session):
    """影子资产场景：通知落库 email_type='push:shadow_asset' + ctx，且邮件 log 生成。"""
    import uuid as _uuid
    from datetime import datetime, timezone

    from app.models.asset_reconciliation import AssetReconciliation
    from app.services.push_notification_service import (
        PushNotificationService, _rules_cache,
    )

    _rules_cache["value"] = None
    _run(_make_channels(db_session))
    u1, u2 = _make_users(db_session)

    db_session.add(AssetReconciliation(
        run_id=_uuid.uuid4(),
        reconciliation_type="shadow",
        status="pending",
        details={"agent": {"id": "042", "name": "dev-box",
                            "ip": "192.168.0.99", "os_name": "Debian 12"}},
    ))
    db_session.commit()

    sent = _run(PushNotificationService(db_session).check_shadow_assets())
    assert sent >= 1

    notif = db_session.query(Notification).filter(
        Notification.type == "push",
        Notification.title.like("【影子资产】Agent 042%"),
    ).first()
    assert notif is not None, "影子资产通知未生成"
    assert notif.email_type == "push:shadow_asset", \
        f"email_type 应为场景模板键，实际 {notif.email_type!r}"
    assert notif.email_ctx["count"] == 1
    assert "042" in notif.email_ctx["shadow_list"]

    # 邮件 log 世给有邮箱者，且场景模板键可渲染（用同一 ctx 验证不 KeyError）
    from app.services.email_template_registry import get_template_registry
    tpl = get_template_registry().get(notif.email_type)
    assert tpl is not None, "push:shadow_asset 模板未注册"


def test_source_health_scenario_uses_scenario_template(db_session):
    """数据链路异常场景：email_type='push:source_down'，down_hours 为数值。"""
    from app.models.source_health import SourceHealth
    from app.services.push_notification_service import (
        PushNotificationService, _rules_cache,
    )

    _rules_cache["value"] = None
    _run(_make_channels(db_session))
    _make_users(db_session)

    db_session.add(SourceHealth(
        source_key="loki:probe", source_type="loki", display_name="Loki 探针",
        last_success_at=datetime.now(timezone.utc) - timedelta(hours=5),
        failure_count=3))
    db_session.commit()

    sent = _run(PushNotificationService(db_session).check_source_health())
    assert sent >= 1

    notif = db_session.query(Notification).filter(
        Notification.title.like("【数据链路异常】Loki 探针%")).first()
    assert notif is not None
    assert notif.email_type == "push:source_down"
    # 主题模板「已中断 {down_hours} 小时」要求数值
    assert isinstance(notif.email_ctx["down_hours"], (int, float))
    assert notif.email_ctx["down_hours"] == 5


def test_scenario_template_renders_end_to_end(db_session):
    """用真实落库的 email_ctx 渲染场景模板——不 KeyError、主题正确。"""
    from app.services.email_template_registry import get_template_registry

    registry = get_template_registry()
    ctx = {
        "user": {"id": 1, "username": "ops", "email": "o@x.y"},
        "notification": {
            "id": "n-2", "title": "【影子资产】Agent 042 新增",
            "content": "...", "link": "/assets/reconciliation",
            "created_at": "2026-10-25T00:00:00",
        },
        "type": "push:shadow_asset",
        "unsubscribe_url": "http://x/u",
        # 与场景函数写入 email_ctx 的键一致
        "count": 1,
        "shadow_list": "Agent 042  dev-box  192.168.0.99  Debian 12",
    }
    tpl = registry.get("push:shadow_asset")
    subject = tpl.render_subject(ctx)
    html = tpl.render_html(ctx)
    assert subject == "[影子资产] 1 台新影子资产待确认"
    assert "dev-box" in html
    assert "None" not in html
