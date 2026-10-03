"""图谱查询性能时延采集 + perf 聚合单例（OH-3.6）

职责：
  - 维护 4 类图查询的滑动窗口时延样本（neighbors / paths / impact_scope / chokepoints）
  - 暴露 ``record(endpoint, latency_ms, ok, ts=None)`` / ``snapshot()`` / ``reset()``
  - 暴露 ``slow_queries(max_n)``：从 ring buffer 取最近 N 条超阈值慢查询

设计依据：
  - docs/design/2026-09-30-资产管理AI能力建设-实施方案.md OH-3.6 / 3.7
  - docs/design/2026-10-03-资产管理AI能力建设-任务进度跟踪.md §五 T-3
    （环形缓冲必须线程安全；sample window size=200）

边界（不要做的事）：
  - **不**做 Prometheus exporter（项目无 Prometheus 栈；后续 OH-3.7 自己落库告警即可）
  - **不**做磁盘持久化（重启丢历史可接受；与 stats.py 一致）
  - **不**做全局时延采集（仅 4 类图查询；OH-3.7 扩展时再加）
"""
from __future__ import annotations

import threading
import time
from collections import deque
from typing import Optional

# ---------------------------------------------------------------------------
# 常量（OH-3.6 + OH-3.7 共用）
# ---------------------------------------------------------------------------

WINDOW_SIZE = 200              # 每端点滑动窗口样本上限（防内存爆炸）
SLOW_THRESHOLD_MS_DEFAULT = 500.0   # P95 阈值默认（OH-3.7 触发钉钉告警时复用）
RECENT_SLOW_CAPACITY = 50       # 慢查询 ring buffer（前端「最近慢查询」用）

# 4 类端点（前端看板 P95 卡片顺序与按钮命中即对应此顺序）
QUERY_TYPES: tuple[str, ...] = (
    "neighbors",        # ① GET /graph/assets/{id}/neighbors
    "paths",            # ② GET /graph/paths
    "impact_scope",     # ③ POST /graph/impact-scope
    "vuln_chokepoints", # ④ GET /graph/vuln-chokepoints
)


# ---------------------------------------------------------------------------
# 滑窗样本（deque(maxlen=WINDOW_SIZE) 线程安全由 _LOCK 串行化写入）
# ---------------------------------------------------------------------------

_samples: dict[str, deque[float]] = {t: deque(maxlen=WINDOW_SIZE) for t in QUERY_TYPES}
# 慢查询 ring buffer：(ts_monotonic, latency_ms, query_type, asset_key)
_recent_slow: deque[tuple[float, float, str, Optional[str]]] = deque(maxlen=RECENT_SLOW_CAPACITY)
_LOCK = threading.Lock()


def record(
    query_type: str,
    latency_ms: float,
    *,
    ok: bool = True,
    asset_key: Optional[str] = None,
    slow_threshold_ms: float = SLOW_THRESHOLD_MS_DEFAULT,
) -> None:
    """登记一次图查询耗时。

    Args:
        query_type: 端点键，必须在 ``QUERY_TYPES`` 中；否则静默丢弃（避免脏数据污染 P95）
        latency_ms: 实测耗时（毫秒）
        ok: True=正常返回 / False=抛异常或 5xx（仅 ok=True 入样本桶；失败仍记慢查询便于诊断）
        asset_key: 资产键（仅慢查询带；减少内存）
        slow_threshold_ms: 超过此值即视为慢查询（落 ``_recent_slow`` ring buffer）
    """
    if query_type not in _samples:
        return
    ts = time.monotonic()
    with _LOCK:
        if ok:
            _samples[query_type].append(float(latency_ms))
        if latency_ms >= slow_threshold_ms:
            _recent_slow.append((ts, float(latency_ms), query_type, asset_key))


def _percentile(values: list[float], pct: float) -> float:
    """简单线性插值 percentile（0 ≤ pct ≤ 1）。空样本返回 0.0。"""
    if not values:
        return 0.0
    sorted_v = sorted(values)
    if len(sorted_v) == 1:
        return float(sorted_v[0])
    k = (len(sorted_v) - 1) * pct
    f = int(k)
    c = min(f + 1, len(sorted_v) - 1)
    if f == c:
        return float(sorted_v[f])
    return float(sorted_v[f] + (sorted_v[c] - sorted_v[f]) * (k - f))


def snapshot() -> dict:
    """返回当前滑窗快照（前端 P95 看板 + OH-3.7 告警判断共用）。

    Output shape:
      {
        "window_size": int,                 # 窗口上限（不是实际样本数）
        "samples": {endpoint: int},         # 实际样本数
        "p50_ms":   {endpoint: float},
        "p95_ms":   {endpoint: float},
        "max_ms":   {endpoint: float},
        "avg_ms":   {endpoint: float},
        "slow_count": {endpoint: int},      # 当前窗口内超阈值条数
        "slow_threshold_ms": float,
      }
    """
    with _LOCK:
        out = {
            "window_size": WINDOW_SIZE,
            "samples": {},
            "p50_ms": {},
            "p95_ms": {},
            "max_ms": {},
            "avg_ms": {},
            "slow_count": {},
            "slow_threshold_ms": SLOW_THRESHOLD_MS_DEFAULT,
        }
        for q in QUERY_TYPES:
            vs = list(_samples[q])
            out["samples"][q] = len(vs)
            out["p50_ms"][q] = round(_percentile(vs, 0.50), 2)
            out["p95_ms"][q] = round(_percentile(vs, 0.95), 2)
            out["max_ms"][q] = round(max(vs) if vs else 0.0, 2)
            out["avg_ms"][q] = round((sum(vs) / len(vs)) if vs else 0.0, 2)
            out["slow_count"][q] = sum(1 for v in vs if v >= SLOW_THRESHOLD_MS_DEFAULT)
    return out


def slow_queries(max_n: int = 10) -> list[dict]:
    """返回最近 ``max_n`` 条慢查询（按时间倒序）。

    用于前端「最近慢查询」面板 + OH-3.7 落库告警。
    """
    if max_n <= 0:
        return []
    with _LOCK:
        items = list(_recent_slow)[-max_n:][::-1]
    out = []
    for ts, latency_ms, query_type, asset_key in items:
        out.append({
            "latency_ms": round(latency_ms, 2),
            "query_type": query_type,
            "asset_key": asset_key,
            "ts": ts,
        })
    return out


def reset() -> None:
    """清空全部样本 + 慢查询 ring buffer（仅测试 / OH-3.8 扩容后基线用）。"""
    with _LOCK:
        for q in QUERY_TYPES:
            _samples[q].clear()
        _recent_slow.clear()


# ---------------------------------------------------------------------------
# 装饰器：在 4 个 graph query 函数外套一层时延采集
# ---------------------------------------------------------------------------

import functools
from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable[..., dict])


def observe(query_type: str) -> Callable[[F], F]:
    """为 graph 4 类查询函数加时延采集装饰器。

    用法：
        @observe("neighbors")
        def get_neighbors(...): ...

    注意：
      - 仅装饰 query.py 内的 4 个函数；其它位置不挂
      - 函数返回 dict 即视为成功；抛异常即 ok=False（仍会入慢查询 ring buffer 便于诊断）
      - **不**改变函数签名 / 返回值（透明装饰器）
    """
    if query_type not in QUERY_TYPES:
        raise ValueError(f"observe() 拒绝未注册 query_type: {query_type!r}")

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            t0 = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                latency_ms = (time.perf_counter() - t0) * 1000.0
                # 第二位置若为 db: Session 则跳过；从 kwargs 找 asset_key
                asset_key = kwargs.get("center_node_key") or kwargs.get("asset_key")
                if asset_key is None and len(args) >= 2 and isinstance(args[1], str):
                    asset_key = args[1]
                record(query_type, latency_ms, ok=True, asset_key=asset_key)
                return result
            except Exception:
                latency_ms = (time.perf_counter() - t0) * 1000.0
                asset_key = kwargs.get("center_node_key") or kwargs.get("asset_key")
                if asset_key is None and len(args) >= 2 and isinstance(args[1], str):
                    asset_key = args[1]
                record(query_type, latency_ms, ok=False, asset_key=asset_key)
                raise

        return wrapper  # type: ignore[return-value]

    return decorator
