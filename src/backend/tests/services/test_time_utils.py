"""P1-T5：时间/时区工具单测"""
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

# 让 pytest 在不装包时也能找到 app.*
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.time_utils import (
    UTC,
    NS_PER_SECOND,
    utc_now,
    ensure_utc,
    datetime_to_loki_ns,
    loki_ns_to_datetime,
    split_time_window,
    merge_time_windows,
)


def test_utc_now_has_tzinfo():
    """utc_now 必须返回带 tzinfo=UTC 的 datetime。"""
    n = utc_now()
    assert n.tzinfo is not None
    assert n.utcoffset() == timedelta(0)


def test_ensure_utc_naive_assumed_utc():
    """naive datetime 被假定为 UTC 并补 tzinfo。"""
    naive = datetime(2026, 1, 1, 0, 0, 0)
    out = ensure_utc(naive)
    assert out.tzinfo is UTC
    assert out.year == 2026 and out.hour == 0


def test_ensure_utc_aware_converted_to_utc():
    """aware datetime 转 UTC：例如 +08:00 转 UTC。"""
    cst = timezone(timedelta(hours=8))
    aware = datetime(2026, 1, 1, 8, 0, 0, tzinfo=cst)
    out = ensure_utc(aware)
    assert out.tzinfo is UTC
    assert out.hour == 0  # 08:00 +08 == 00:00 UTC


def test_datetime_to_loki_ns_roundtrip():
    """datetime ↔ Loki 纳秒往返。"""
    dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    ns = datetime_to_loki_ns(dt)
    assert ns == int(dt.timestamp() * NS_PER_SECOND)
    rt = loki_ns_to_datetime(ns)
    assert rt == dt


def test_loki_ns_to_datetime_accepts_string():
    """Loki 返回的时间戳有时是字符串，工具要能吃。"""
    dt = datetime(2026, 6, 15, 12, 30, 45, tzinfo=UTC)
    ns = str(datetime_to_loki_ns(dt))
    rt = loki_ns_to_datetime(ns)
    assert rt == dt


def test_split_time_window_left_closed_right_open():
    """窗口切分：左闭右开，且并集 == 原窗口，无重叠。"""
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = start + timedelta(hours=2, minutes=30)
    parts = split_time_window(start, end, step=timedelta(hours=1))
    assert len(parts) == 3
    # 第一段 [0:00, 1:00)
    assert parts[0] == (start, start + timedelta(hours=1))
    # 第二段 [1:00, 2:00)
    assert parts[1] == (start + timedelta(hours=1), start + timedelta(hours=2))
    # 第三段 [2:00, 2:30)（剩余 30 分钟）
    assert parts[2] == (start + timedelta(hours=2), end)

    # 验证无重叠且并集 == 原窗口
    s = parts[0][0]
    e = parts[-1][1]
    for i in range(1, len(parts)):
        assert parts[i][0] == parts[i - 1][1]  # 无重叠
    assert s == start and e == end


def test_split_time_window_invalid_args():
    """start >= end 返回空；step <= 0 抛错。"""
    s = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    assert split_time_window(s, s) == []
    assert split_time_window(s, s - timedelta(seconds=1)) == []
    try:
        split_time_window(s, s + timedelta(hours=1), step=timedelta(0))
        assert False, "should raise"
    except ValueError:
        pass


def test_merge_time_windows_overlapping():
    """重叠窗口合并。"""
    w1 = (datetime(2026, 1, 1, 0, tzinfo=UTC), datetime(2026, 1, 1, 2, tzinfo=UTC))
    w2 = (datetime(2026, 1, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, 3, tzinfo=UTC))
    out = merge_time_windows([w1, w2])
    assert out == [(datetime(2026, 1, 1, 0, tzinfo=UTC), datetime(2026, 1, 1, 3, tzinfo=UTC))]


def test_merge_time_windows_disjoint():
    """不相邻窗口不被合并。"""
    w1 = (datetime(2026, 1, 1, 0, tzinfo=UTC), datetime(2026, 1, 1, 1, tzinfo=UTC))
    w2 = (datetime(2026, 1, 1, 2, tzinfo=UTC), datetime(2026, 1, 1, 3, tzinfo=UTC))
    out = merge_time_windows([w1, w2])
    assert out == [w1, w2]


def test_24h_7d_consistency():
    """24h 窗口与 7d 窗口不存在重复/遗漏边界点（P1-T5 验收）。"""
    end = datetime(2026, 6, 1, 0, 0, 0, tzinfo=UTC)
    start_24h = end - timedelta(hours=24)
    start_7d = end - timedelta(days=7)

    # 切分 7d 成 7 个 24h，全部首尾相接
    parts = split_time_window(start_7d, end, step=timedelta(hours=24))
    assert len(parts) == 7
    assert parts[0][0] == start_7d
    assert parts[-1][1] == end
    for i in range(1, len(parts)):
        assert parts[i][0] == parts[i - 1][1]

    # 第 6 段 = [start_7d + 6d, end) == 24h 窗口
    six_day = parts[6]
    assert six_day == (start_24h, end)