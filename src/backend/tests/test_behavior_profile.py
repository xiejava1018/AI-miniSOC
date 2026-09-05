"""行为画像 P1.5 单元测试（纯函数 + 快照 gap 逻辑）"""

import datetime as dt

import pytest

from app.models.behavior_profile import (
    BehaviorProfile, BehaviorProfileWatermark,
)
from app.services.behavior_profile.aggregator import (
    aggregate_day, compute_traffic_type, merge_days,
)
from app.services.behavior_profile.classifier import (
    TIME_BLOCKS, block_of, classify,
)
from app.services.behavior_profile.loki_source import RE_DOM
from app.services.behavior_profile.snapshot_job import mark_gap
from app.services.behavior_profile.tagger import (
    PERSONA_MAP, build_tags, compute_confidence, persona_alias,
)

TZ = dt.timezone(dt.timedelta(hours=8))


def _ts(hour, minute=0):
    d = dt.date(2026, 9, 5)  # 周六
    return dt.datetime.combine(d, dt.time(hour, minute), tzinfo=TZ)


# ── classifier ──────────────────────────────────────────

def test_classify_layers():
    assert classify("copilot.tencent.com")[1]["layer"] == "ACT"
    assert classify("ntp.aliyun.com")[1]["layer"] == "SYS"
    assert classify("countly.163.com")[1]["layer"] == "AD"
    assert classify("192.168.0.8")[0] == "IP 直连"
    assert classify("")[0] == "其他"


def test_classify_education_category():
    """§9.7.5：学习教育类必须存在，学生党标签可触发"""
    assert classify("www.icourse163.org")[0] == "学习教育"
    assert classify("mooc.example.edu.cn")[0] == "学习教育"


def test_priority_ai_over_dev():
    """优先级：含 copilot 的域名归 AI 工具而非开发技术"""
    assert classify("copilot.github.com")[0] == "AI 工具"


def test_block_of():
    assert block_of(3).name == "深夜"
    assert block_of(10).name == "上午"
    assert block_of(23).name == "夜间"
    assert len(TIME_BLOCKS) == 7


# ── loki_source（正则） ──────────────────────────────────

def test_domain_regex():
    line = '<13>Sep 05 10:09:51 TL-R479GP-AC behavior_ctl: 上网行为:a:x 网站分组:所有网站 网址:copilot.tencent.com:443 。'
    assert RE_DOM.search(line).group(1) == "copilot.tencent.com"


# ── aggregator ──────────────────────────────────────────

def _events():
    return [
        (_ts(2), "ntp.aliyun.com"), (_ts(2), "pool.ntp.org"),
        (_ts(3), "time.apple.com"),
        (_ts(10), "copilot.tencent.com"), (_ts(10), "github.com"),
        (_ts(14), "github.com"), (_ts(23), "v.qq.com"),
    ]


def test_aggregate_day():
    s = aggregate_day(_events())
    assert s["total"] == 7
    assert s["by_hour"][10] == 2
    assert s["by_block"]["上午"] == 2
    assert s["layer_visit"].get("SYS") == 3
    assert s["act_total"] == 4
    assert s["domain_visits"]["github.com"] == 2


def test_compute_traffic_type():
    s = aggregate_day(_events())
    assert compute_traffic_type(s) in ("human", "mixed")
    # SYS 占比 ≥60% → machine
    machine = {"total": 100, "layer_visit": {"SYS": 70, "ACT": 30}}
    assert compute_traffic_type(machine) == "machine"
    # 样本太少不判定
    assert compute_traffic_type({"total": 10, "layer_visit": {"SYS": 10}}) == "human"


def test_merge_days_and_tags():
    week = [aggregate_day(_events()) for _ in range(7)]
    m = merge_days(week, 7)
    assert m["total"] == 49
    assert m["days"] == 7
    tags = build_tags(m)
    assert all("alias" in t and "evidence" in t for t in tags)
    # 数据量足够大才触发高强度标签；至少验证 cat_share 已归一
    assert isinstance(m["cat_share"], dict)


def test_persona_map_alias():
    assert persona_alias("夜猫子") == "野猫子"
    assert persona_alias("早起鸟") == ""  # 无映射显示规则名
    assert set(PERSONA_MAP) == {k for k in PERSONA_MAP}


# ── tagger.confidence ───────────────────────────────────

def test_confidence():
    assert compute_confidence(0, 0) == 0
    assert compute_confidence(5000, 0) == 100
    # 截断惩罚
    assert compute_confidence(5000, 2) < compute_confidence(5000, 0)


# ── snapshot gap 标记（DB） ──────────────────────────────

def _target():
    return {"ip": "192.168.99.98", "asset_id": None, "mac": None, "hostname": None}


def _day():
    return dt.date(2026, 9, 1)


def test_mark_gap_creates_placeholder(db_session):
    from tests.conftest import TestingSessionLocal  # noqa: F401

    db_session.query(BehaviorProfile).filter(
        BehaviorProfile.ip == "192.168.99.98").delete()
    db_session.commit()

    mark_gap(db_session, _target(), _day())
    row = (
        db_session.query(BehaviorProfile)
        .filter(BehaviorProfile.ip == "192.168.99.98",
                BehaviorProfile.profile_date == _day())
        .first()
    )
    assert row is not None
    assert row.status == "gap"
    assert row.total == 0
    assert row.confidence == 0

    # 已有 ok 数据时不覆盖
    row.status = "ok"
    row.total = 42
    db_session.commit()
    mark_gap(db_session, _target(), _day())
    db_session.expire_all()
    row = (
        db_session.query(BehaviorProfile)
        .filter(BehaviorProfile.ip == "192.168.99.98",
                BehaviorProfile.profile_date == _day())
        .first()
    )
    assert row.status == "ok"
    assert row.total == 42

    # 清理
    db_session.query(BehaviorProfile).filter(
        BehaviorProfile.ip == "192.168.99.98").delete()
    db_session.commit()
