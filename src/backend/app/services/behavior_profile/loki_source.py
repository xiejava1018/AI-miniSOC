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

# ── DNS 反查（PTR）噪声过滤 ────────────────────────────────
# TP-Link behavior_ctl 会把客户端每次 DNS 反查（即使失败、即使无人使用其结果）
# 也记成一条上网行为，域名载体形如 `1.0.168.192.in-addr.arpa`。
# 这类记录不代表任何人的上网意图，却会：
#   1) 把cat_share 的"其他"类撑到接近 100%（实测 .42 主体 98% 域名是 PTR）；
#   2) 挤占 top_domains 前 N 名（实测 PTR 域名排到第 2~5 位）；
#   3) 虚增 total / by_hour，让"夜猫子"等作息标签失真。
# 必须在**入库前**丢弃，事后无法从聚合结果里还原。
#
# 覆盖 IPv4 反查（in-addr.arpa）与 IPv6 反查（ip6.arpa）。
# 刻意不做"解析成功才保留"——反查结果是否有意义无从判断，
# 且 PTR 域名不携带用户意图，一律丢弃语义最干净。
RE_PTR_ARPA = re.compile(r"\.(?:in-addr\.arpa|ip6\.arpa)\.?$")


def is_ptr_lookup(domain: str) -> bool:
    """判断是否为 DNS 反查域名（PTR），应在入库前丢弃。

    独立成函数便于 classifier 侧做二次防御，也便于单测直接覆盖。
    """
    return bool(RE_PTR_ARPA.search((domain or "").lower().strip()))


def _loki_base() -> str:
    # 配置中心 v1（X1E-11）：从 data_source_resolver 读 loki
    from app.services.data_source_resolver import get_endpoint
    return (get_endpoint("loki") or settings.LOKI_API_URL).rstrip("/")


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

    DNS 反查（PTR）记录在此处**入库前**丢弃——见RE_PTR_ARPA 处的说明。
    """
    start = dt.datetime.combine(day, dt.time.min, tzinfo=TZ)
    end = start + dt.timedelta(days=1)
    events: List[Tuple[dt.datetime, str]] = []
    stats = [0, 0]
    ptr_dropped = 0
    for ts, line in pull_window(ip, start, end, stats=stats):
        m = RE_DOM.search(line)
        if not m:
            continue
        domain = m.group(1).lower()
        if is_ptr_lookup(domain):
            ptr_dropped += 1
            continue
        d = dt.datetime.fromtimestamp(ts / 1e9, TZ)
        events.append((d, domain))
    if ptr_dropped:
        # 逐日计数而非总量，避免高频主体刷屏；与 total=0 一样值得被看见（§4.1 假绿防护）
        logger.info("过滤 DNS 反查噪声 ip=%s day=%s dropped=%d kept=%d",
                    ip, day, ptr_dropped, len(events))
    return events, stats
