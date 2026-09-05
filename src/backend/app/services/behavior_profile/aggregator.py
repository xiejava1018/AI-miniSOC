"""行为聚合器（从 POC scripts/behavior_profile_collect.py 迁入）

单日聚合：把某一天的原始事件聚合成快照行的全部分布字段。
滚动聚合：把最近 N 天的单日聚合合并成 7 天口径，供 tags / cat_share 使用。

计数口径与 POC 一致：逐条原始日志时间戳计数（§9.7.7 禁 count_over_time）。
"""

import datetime as dt
from collections import Counter, defaultdict
from typing import Dict, Iterable, List, Sequence, Tuple

from .classifier import BLOCK_ORDER, CATEGORIES, block_of, classify


def aggregate_day(events: Sequence[Tuple[dt.datetime, str]]) -> dict:
    """把单日事件聚合成日快照统计。

    events: [(本地datetime, 域名), ...]
    返回 {total, by_hour, wd_hour, by_block, domain_visits, layer_visit, act_total, night_share,...}
    """
    by_hour = [0] * 24
    wd_hour = [[0] * 24 for _ in range(7)]
    by_block = {b: 0 for b in BLOCK_ORDER}
    domain_visits: Counter = Counter()
    cat_visit: Counter = Counter()

    for d, dom in events:
        h = d.hour
        by_hour[h] += 1
        wd_hour[d.weekday()][h] += 1
        by_block[block_of(h).name] += 1
        domain_visits[dom] += 1

    for dom, n in domain_visits.items():
        cat_visit[classify(dom)[0]] += n

    layer_visit: Counter = Counter()
    for cat, v in cat_visit.items():
        layer_visit[CATEGORIES.get(cat, {}).get("layer", "ACT")] += v

    total = sum(by_hour)
    return {
        "total": total,
        "by_hour": by_hour,
        "wd_hour": wd_hour,
        "by_block": by_block,
        "domain_visits": dict(domain_visits),
        "cat_visit": dict(cat_visit),
        "layer_visit": dict(layer_visit),
        "act_total": layer_visit.get("ACT", 0),
        "night_share": round(sum(by_hour[:6]) / total * 100, 1) if total else 0,
        "morning_share": round(sum(by_hour[6:9]) / total * 100, 1) if total else 0,
        "workhours_share": round(sum(by_hour[9:19]) / total * 100, 1) if total else 0,
        "evening_share": round(sum(by_hour[19:24]) / total * 100, 1) if total else 0,
        "workday": sum(sum(wd_hour[i]) for i in range(5)),
        "weekend": sum(sum(wd_hour[i]) for i in range(5, 7)),
    }


def compute_traffic_type(day_stat: dict) -> str:
    """机器流量判定（§9.7.1，P0）。

    SYS 层占比 ≥60% 或（数据量足够时）分布高度集中于少数域名且无时段起伏
    → machine；两者之间 → mixed。
    """
    total = day_stat.get("total", 0)
    if total < 50:
        return "human"  # 样本太少不判定，按人对待并让 confidence 说话
    lv = day_stat.get("layer_visit", {})
    sys_ratio = lv.get("SYS", 0) / total
    if sys_ratio >= 0.6:
        return "machine"
    if sys_ratio >= 0.4:
        return "mixed"
    return "human"


def merge_days(day_stats: Iterable[dict], days_span: int) -> dict:
    """把多个单日聚合合并成滚动窗口聚合（供 tags / cat_share 计算）。

    day_stats: 各日 aggregate_day 结果（可含 None/空）
    days_span: 窗口自然日数（如 7），用于 workday/weekend 归一化
    """
    by_hour = [0] * 24
    wd_hour = [[0] * 24 for _ in range(7)]
    by_block = {b: 0 for b in BLOCK_ORDER}
    domain_visits: Counter = Counter()
    cat_visit: Counter = Counter()
    active_hours = set()
    workday = weekend = 0

    for s in day_stats:
        if not s or not s.get("total"):
            continue
        for h in range(24):
            by_hour[h] += s["by_hour"][h]
            if s["by_hour"][h] > 0:
                active_hours.add((id(s), h))
        for i in range(7):
            for h in range(24):
                wd_hour[i][h] += s["wd_hour"][i][h]
        for b in BLOCK_ORDER:
            by_block[b] += s["by_block"].get(b, 0)
        domain_visits.update(s["domain_visits"])
        cat_visit.update(s["cat_visit"])
        workday += s.get("workday", 0)
        weekend += s.get("weekend", 0)

    layer_visit: Counter = Counter()
    for cat, v in cat_visit.items():
        layer_visit[CATEGORIES.get(cat, {}).get("layer", "ACT")] += v
    total = sum(by_hour)
    act_total = layer_visit.get("ACT", 0)
    cat_share = {
        c: round(v / act_total * 100, 1)
        for c, v in cat_visit.items()
        if CATEGORIES.get(c, {}).get("layer", "ACT") == "ACT" and act_total
    }
    cat_share = dict(sorted(cat_share.items(), key=lambda t: -t[1]))
    top6_share = round(sum(sorted(by_hour, reverse=True)[:6]) / total * 100, 1) if total else 0

    return {
        "total": total,
        "days": days_span,
        "daily_avg": round(total / max(days_span, 1)),
        "by_hour": by_hour,
        "wd_hour": wd_hour,
        "by_block": by_block,
        "domain_count": len(domain_visits),
        "top_domains": [
            {"domain": d, "visits": v, "category": classify(d)[0],
             "share": round(v / total * 100, 2)}
            for d, v in domain_visits.most_common(20)
        ],
        "cat_visit": dict(cat_visit.most_common()),
        "cat_share": cat_share,
        "layer_visit": dict(layer_visit),
        "act_total": act_total,
        "active_hours": len(active_hours),
        "peak_hour": max(range(24), key=lambda h: by_hour[h]) if total else 0,
        "top6_share": top6_share,
        "workday": workday,
        "weekend": weekend,
        "night_share": round(sum(by_hour[:6]) / total * 100, 1) if total else 0,
        "morning_share": round(sum(by_hour[6:9]) / total * 100, 1) if total else 0,
        "workhours_share": round(sum(by_hour[9:19]) / total * 100, 1) if total else 0,
        "evening_share": round(sum(by_hour[19:24]) / total * 100, 1) if total else 0,
    }
