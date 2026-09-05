"""Phase 0 身份管道测试：正则抽取 + 关系查询（不依赖 OpenSearch）"""

import datetime as dt

import pytest

from app.models.identity import IdentityBinding, IdentityEvent
from app.services.behavior_profile.identity import (
    _extract,
    _rule_event_type,
    get_relations,
)


# ── 抽取正则 ─────────────────────────────────────────────

def test_extract_ssh_accepted():
    log = ("Sep 01 11:59:58 host sshd[680397]: Accepted publickey for xiejava "
           "from 192.168.0.8 port 54077 ssh2")
    account, srcip = _extract(log, "5715")
    assert account == "xiejava"
    assert srcip == "192.168.0.8"


def test_extract_ssh_failed_invalid_user():
    log = "Sep 01 11:00:00 host sshd[1]: Failed password for invalid user admin from 1.2.3.4 port 22 ssh2"
    account, srcip = _extract(log, "5760")
    assert account == "admin"
    assert srcip == "1.2.3.4"


def test_extract_pam_session_open():
    account, _ = _extract("session opened for user(root) by (uid=0)", "5501")
    assert account == "root"


def test_rule_event_type():
    assert _rule_event_type("5715", "")[1] is True
    assert _rule_event_type("5760", "")[1] is False
    assert _rule_event_type("5501", "")[0] == "session_open"


# ── 关系查询 ─────────────────────────────────────────────

def _ev(ip, account, dst, success=True, n=1):
    base = dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc)
    for i in range(n):
        yield IdentityEvent(
            es_index="wazuh-alerts-4.x-2026.09.01", es_doc_id=f"{ip}-{account}-{dst}-{i}",
            rule_id="5715", account=account, src_ip=ip, dst_ip=dst,
            success=success, event_type="auth_success" if success else "auth_failed",
            ts=base + dt.timedelta(hours=i),
        )


@pytest.fixture()
def _seed_identity(db_session):
    # xiejava 从 .8 登录 .102（成功 3 次）
    db_session.add_all(list(_ev("192.168.0.8", "xiejava", "192.168.0.102", True, 3)))
    # root 从 .8 登录 .102（成功 1 次）→ 设备共享度 = 2
    db_session.add_all(list(_ev("192.168.0.8", "root", "192.168.0.102", True, 1)))
    # 外部 1.2.3.4 攻击 .102（失败 2 次）
    db_session.add_all(list(_ev("1.2.3.4", "admin", "192.168.0.102", False, 2)))
    db_session.add(IdentityBinding(account="xiejava", ip="192.168.0.102", logins=3))
    db_session.commit()
    yield
    db_session.query(IdentityEvent).delete()
    db_session.query(IdentityBinding).delete()
    db_session.commit()


def test_get_relations_inbound(db_session, _seed_identity):
    r = get_relations(db_session, "192.168.0.102")
    assert r["device_shared_by"] == 2
    assert set(r["accounts_on_host"]) == {"xiejava", "root"}
    assert r["inbound_fail_total"] == 2
    assert r["external_attackers"] and r["external_attackers"][0]["ip"] == "1.2.3.4"
    inbound_map = {x["account"]: x["count"] for x in r["inbound"]}
    assert inbound_map["xiejava"] == 3


def test_get_relations_outbound(db_session, _seed_identity):
    r = get_relations(db_session, "192.168.0.8")
    assert any(x["ip"] == "192.168.0.102" for x in r["outbound"])
