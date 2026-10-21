"""DNS 反查（PTR）噪声过滤测试

背景：TP-Link behavior_ctl 把客户端每次 DNS 反查（即使失败、即使结果无人使用）
也记成一条上网行为，域名载体形如 `1.0.168.192.in-addr.arpa`。
实测该噪声会让某主体的 cat_share 变成 {"其他": 100.0}、98% 域名是 PTR。

过滤分两层：
  1. loki_source.fetch_day_events —— 入库前丢弃（主防线）
  2. classifier.classify —— 二次防御，挡历史脏数据 / 其他写入方
"""

import datetime as dt

import pytest

from app.services.behavior_profile.classifier import classify
from app.services.behavior_profile.loki_source import (
    RE_DOM, fetch_day_events, is_ptr_lookup,
)

TZ = dt.timezone(dt.timedelta(hours=8))


# ── is_ptr_lookup ────────────────────────────────────────
@pytest.mark.parametrize("domain", [
    "1.0.168.192.in-addr.arpa",
    "173.0.168.192.in-addr.arpa",
    "10.0.168.192.in-addr.arpa",
    "122.0.168.192.in-addr.arpa",
    "1.0.168.192.IN-ADDR.ARPA",            # 大写（函数内已 lower）
    "1.0.168.192.in-addr.arpa.",           # 尾点
    "abc.ip6.arpa",
    "  1.0.168.192.in-addr.arpa  ",        # 前后空白
])
def test_is_ptr_lookup_true(domain):
    assert is_ptr_lookup(domain) is True


@pytest.mark.parametrize("domain", [
    "version.goauthentik.io",
    "open.feishu.cn",
    "www.workbuddy.cn",
    "stun-heyuan-v6.easytier.cn",
    "in-addr.arpa.com",                   # 只作前缀，不是反查域
    "in-addr.arpa",                       # 裸 arpa 域（无前导标签）非真实 PTR 形式
    "notarpa.io",
    "arpa",
    "",
    None,
])
def test_is_ptr_lookup_false(domain):
    assert is_ptr_lookup(domain) is False


# ── classifier 二次防御 ──────────────────────────────────
def test_classify_ptr_goes_to_system_background():
    """PTR 归入"系统背景"（机器行为），不是"其他"（人的兴趣）。"""
    cat, _ = classify("1.0.168.192.in-addr.arpa")
    assert cat == "系统背景"


def test_classify_normal_domain_unaffected():
    """正常域名分类不受影响。"""
    assert classify("open.feishu.cn")[0] == "工作办公"
    assert classify("www.workbuddy.cn")[0] == "开发技术"


def test_classify_ip_direct_still_works():
    """裸 IP 仍走"IP 直连"，不能被 PTR 规则抢走。"""
    assert classify("202.118.1.81")[0] == "IP 直连"


# ── fetch_day_events 入库前过滤 ──────────────────────────
def _line(ts, body):
    """构造一条 Alloy 已解包的行为日志行（body 为 JSON 字符串）。"""
    import json
    return (ts, json.dumps({"body": body}, ensure_ascii=False))


def test_fetch_day_events_drops_ptr(monkeypatch):
    """PTR 记录不进events；正常域名保留。"""
    import json

    day = dt.date(2026, 10, 21)
    start = dt.datetime.combine(day, dt.time.min, tzinfo=TZ)
    base_ns = int(start.timestamp() * 1_000_000_000)

    rows = [
        _line(base_ns + 1_000_000_000,
              "<13>Oct 21 09:09:09 TL-R479GPE-AC behavior_ctl: "
              "a:192.168.0.42 网址:version.goauthentik.io 。"),
        _line(base_ns + 2_000_000_000,
              "<13>Oct 21 09:00:03 TL-R479GPE-AC behavior_ctl: "
              "a:192.168.0.42 网址:238.0.168.192.in-addr.arpa 。"),
        _line(base_ns + 3_000_000_000,
              "<13>Oct 21 09:00:04 TL-R479GPE-AC behavior_ctl: "
              "a:192.168.0.42 网址:open.feishu.cn 。"),
        _line(base_ns + 4_000_000_000,
              "<13>Oct 21 09:00:05 TL-R479GPE-AC behavior_ctl: "
              "a:192.168.0.42 网址:1.0.168.192.in-addr.arpa 。"),
    ]

    monkeypatch.setattr(
        "app.services.behavior_profile.loki_source.pull_window",
        lambda ip, s, e, limit=10000, stats=None: rows,
    )

    events, _stats = fetch_day_events("192.168.0.42", day)
    domains = [d for _, d in events]

    assert "version.goauthentik.io" in domains
    assert "open.feishu.cn" in domains
    assert not any("in-addr.arpa" in d for d in domains), \
        "PTR 反查域名必须在入库前被丢弃"
    assert len(events) == 2


def test_fetch_day_events_all_ptr_yields_empty(monkeypatch):
    """全天都是 PTR 时 events 为空（而不是塞满噪声）。"""
    import json

    day = dt.date(2026, 10, 21)
    base_ns = int(dt.datetime.combine(day, dt.time.min, tzinfo=TZ).timestamp() * 1_000_000_000)
    rows = [
        (base_ns + i * 1_000_000_000,
         json.dumps({"body": f"<13>Oct 21 09:00:0{i%10} TL-R479GPE-AC behavior_ctl: "
                             f"a:192.168.0.42 网址:{i}.0.168.192.in-addr.arpa 。"}))
        for i in range(10)
    ]

    monkeypatch.setattr(
        "app.services.behavior_profile.loki_source.pull_window",
        lambda ip, s, e, limit=10000, stats=None: rows,
    )

    events, _ = fetch_day_events("192.168.0.42", day)
    assert events == []


# ── RE_DOM 未被破坏 ─────────────────────────────────────
def test_re_dom_still_extracts_网址():
    line = ("<13>Oct 21 09:09:09 TL-R479GPE-AC behavior_ctl: "
            "a:192.168.0.42 网址:version.goauthentik.io 。")
    assert RE_DOM.search(line).group(1) == "version.goauthentik.io"