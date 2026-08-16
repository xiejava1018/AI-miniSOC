"""
时间工具（P1-T5 数据可靠性）

统一 AI-miniSOC 的时间/时区处理：
- 所有持久化时间一律 UTC（DateTime(timezone=True) 落库时需带 tzinfo=utc）
- 窗口语义：左闭右开 [start, end)
- Loki 时间戳：纳秒级 Unix 时间戳
- Python datetime 与 Loki/PostgreSQL 间转换

非目标（防范围蔓延）：
- 不引入 pytz/zoneinfo 复杂依赖（只用标准库 datetime.timezone.utc）
- 不改前端展示逻辑（仅保证后端时间一致）
"""

from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Tuple

# 全局常量：UTC 时区别名
UTC = timezone.utc

# 纳秒 ↔ 秒 转换常量（整数无损）
NS_PER_SECOND = 1_000_000_000


def utc_now() -> datetime:
    """返回带 UTC tzinfo 的当前时间（替代 datetime.utcnow()，后者无 tzinfo）。

    Python 3.12+ datetime.utcnow() 已废弃（PEP 495 之后裸 naive datetime 易混）。
    所有持久化时间一律通过本函数获取。
    """
    return datetime.now(UTC)


def ensure_utc(dt: datetime) -> datetime:
    """若 datetime 无 tzinfo，假定为 UTC 并补 tzinfo；若有 tzinfo，转换到 UTC。"""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def datetime_to_loki_ns(dt: datetime) -> int:
    """datetime (UTC) → Loki 纳秒级时间戳。

    Loki /query_range 的 start/end 参数单位为纳秒（int64）。
    """
    utc = ensure_utc(dt)
    return int(utc.timestamp() * NS_PER_SECOND)


def loki_ns_to_datetime(ns: int | str) -> datetime:
    """Loki 纳秒级时间戳 → datetime (UTC)。"""
    return datetime.fromtimestamp(int(ns) / NS_PER_SECOND, tz=UTC)


def split_time_window(
    start: datetime,
    end: datetime,
    *,
    step: timedelta = timedelta(hours=1),
) -> List[Tuple[datetime, datetime]]:
    """将 [start, end) 窗口按 step 切分为多个子窗口（**左闭右开**）。

    用于 P1-T3 Loki 时间分片翻页。返回的子窗口列表保证：
      - 全部并集覆盖 [start, end)
      - 相邻子窗口不重叠
      - 最后一段可能不足 step（保证不漏数据）

    入参自动 ensure_utc；step 必须 > 0。
    """
    if step.total_seconds() <= 0:
        raise ValueError("step must be > 0")

    s = ensure_utc(start)
    e = ensure_utc(end)
    if s >= e:
        return []

    out: List[Tuple[datetime, datetime]] = []
    cur = s
    while cur < e:
        nxt = min(cur + step, e)
        out.append((cur, nxt))
        cur = nxt
    return out


def merge_time_windows(
    windows: Iterable[Tuple[datetime, datetime]],
) -> List[Tuple[datetime, datetime]]:
    """合并重叠/相邻的窗口（用于检测去重与可视聚合）。

    输入输出均为左闭右开。
    """
    normalized = sorted((ensure_utc(s), ensure_utc(e)) for s, e in windows if s < e)
    if not normalized:
        return []

    out: List[Tuple[datetime, datetime]] = []
    cur_s, cur_e = normalized[0]
    for s, e in normalized[1:]:
        if s <= cur_e:
            if e > cur_e:
                cur_e = e
        else:
            out.append((cur_s, cur_e))
            cur_s, cur_e = s, e
    out.append((cur_s, cur_e))
    return out