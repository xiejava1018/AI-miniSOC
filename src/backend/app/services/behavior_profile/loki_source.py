"""Loki 原始日志拉取（从 POC scripts/behavior_profile_collect.py 迁入）

硬约束（方案 §9.7.7，写死）：
  一律用原始日志时间戳逐条计数，禁止 count_over_time 聚合下推做时段统计。
  实测 Loki 的 sum(count_over_time({ip}[1h])) 在 step=1h 下存在
  窗口标签错位（真实 20 点的数据被标到 21 点）与边界重复计数。
  行为画像对时段极敏感——差 1 小时足以把"夜猫子"判成"早起鸟"。
"""

import datetime as dt
import logging
import re
from typing import List, Optional, Tuple

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

TZ = dt.timezone(dt.timedelta(hours=8))
_NS = 1_000_000_000

MIN_WINDOW = dt.timedelta(minutes=15)

# 日志行: 网址:host[:port] —— TP-Link 上网行为日志的域名载体
RE_DOM = re.compile(r"网址:([^\s:：]+)")


def _loki_base() -> str:
    return settings.LOKI_API_URL.rstrip("/")


def _ns(d: dt.datetime) -> str:
    return str(int(d.timestamp() * _NS))


def loki_raw(ip: str, start: dt.datetime, end: dt.datetime,
             limit: int = 10000) -> List[Tuple[int, str]]:
    """拉取某时间窗内的原始日志行，返回 [(ts_ns, line), ...]。"""
    with httpx.Client(timeout=120.0) as c:
        r = c.get(
            f"{_loki_base()}/loki/api/v1/query_range",
            params={
                "query": f'{{ip="{ip}"}}',
                "start": _ns(start),
                "end": _ns(end),
                "limit": str(limit),
                "direction": "forward",
            },
        )
        if r.status_code != 200:
            raise RuntimeError(f"Loki {r.status_code}: {r.text[:200]}")
        out: List[Tuple[int, str]] = []
        for x in r.json()["data"]["result"]:
            out.extend((int(ts), line) for ts, line in x.get("values", []))
        return out


def pull_window(ip: str, start: dt.datetime, end: dt.datetime,
                limit: int = 10000,
                stats: Optional[List[int]] = None) -> List[Tuple[int, str]]:
    """递归自适应分块：单次查询撞到 limit 就把窗口劈成两半再拉。

    stats: [请求数, 截断窗口数]（可累计调用方计数器）。
    已切到 MIN_WINDOW 仍饱和的窗口计入截断数（快照 confidence 降级依据）。
    """
    rows = loki_raw(ip, start, end, limit)
    if stats is not None:
        stats[0] += 1
    if len(rows) >= limit and (end - start) > MIN_WINDOW:
        mid = start + (end - start) / 2
        return (pull_window(ip, start, mid, limit, stats)
                + pull_window(ip, mid, end, limit, stats))
    if len(rows) >= limit and stats is not None:
        stats[1] += 1
    return rows


def fetch_day_events(ip: str, day: dt.date) -> Tuple[List[Tuple[dt.datetime, str]], List[int]]:
    """拉取指定 IP 某天（本地时区一整天）的全部上网行为事件。

    返回 ([(本地datetime, 域名), ...], stats)
    """
    start = dt.datetime.combine(day, dt.time.min, tzinfo=TZ)
    end = start + dt.timedelta(days=1)
    events: List[Tuple[dt.datetime, str]] = []
    stats = [0, 0]
    for ts, line in pull_window(ip, start, end, stats=stats):
        m = RE_DOM.search(line)
        if not m:
            continue
        d = dt.datetime.fromtimestamp(ts / 1e9, TZ)
        events.append((d, m.group(1).lower()))
    return events, stats
