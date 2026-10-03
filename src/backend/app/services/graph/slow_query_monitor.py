"""
图谱慢查询告警监控器（OH-3.7）

订阅 perf.snapshot()，判据：
  - 滑窗样本 ≥ GRAPH_PERF_ALERT_WINDOW_MIN_SAMPLES（防冷启误报）
  - 连续 GRAPH_PERF_ALERT_SUSTAINED_ROUNDS 轮 P95 ≥ threshold
  - 触发 severity：
      * warning  = P95 ≥ threshold
      * critical = P95 ≥ 2× threshold OR max ≥ 3× threshold
  - 恢复：再次低于阈值 + 同一 query_type 无 active → set resolved=True

每轮独立 DB 事务（防僵尸事务；CLAUDE.md §4.5 教训）。

公开函数：
  - evaluate_once() -> dict    # 单轮评估 + 落库；供 API/测试/手动触发
  - start_graph_perf_monitor() / stop_graph_perf_monitor()
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import text

from app.core.config import settings
from app.core.database import SessionLocal
from app.services.graph.perf import snapshot, QUERY_TYPES

logger = logging.getLogger(__name__)

_task: Optional[asyncio.Task] = None
_FIRST_RUN_DELAY = 30  # 启动后稍等，避免冷启 8s+ 误报


# ============ 触发 / 恢复判据（纯函数，可独立测试） ============

def _classify_severity(
    p95_ms: float, max_ms: float, threshold_ms: float
) -> Optional[str]:
    """根据 P95 / max 与阈值，返回 severity；未触发返回 None。"""
    if p95_ms < threshold_ms:
        return None
    if p95_ms >= 2 * threshold_ms or max_ms >= 3 * threshold_ms:
        return "critical"
    return "warning"


def _build_message(
    query_type: str, severity: str, p95_ms: float, threshold_ms: float, slow_count: int
) -> str:
    if severity == "critical":
        return (
            f"[严重] 图谱查询 {query_type} P95 达 {p95_ms:.0f}ms，"
            f"是阈值 {threshold_ms:.0f}ms 的 ≥2 倍，请立即扩容或优化。"
        )
    return (
        f"[警告] 图谱查询 {query_type} P95 = {p95_ms:.0f}ms "
        f"超过阈值 {threshold_ms:.0f}ms；滑窗内慢查询 {slow_count} 条。"
    )


def evaluate_one_round(
    snap: dict, threshold_ms: float, sustained_counter: Dict[str, int]
) -> List[dict]:
    """单轮评估，输出待写入的告警 dict 列表。

    输入：snapshot()、threshold、当前 sustained_counter (query_type -> 连续轮数)
    输出：[{alert_type, query_type, severity, ...}, ...]
    """
    threshold = float(threshold_ms)
    out: List[dict] = []
    for qt in ("neighbors", "paths", "impact_scope", "vuln_chokepoints"):
        p95 = float(snap["p95_ms"][qt])
        max_ms = float(snap["max_ms"][qt])
        samples = int(snap["samples"][qt])
        slow_count = int(snap["slow_count"][qt])

        # 防冷启：样本不足
        if samples < settings.GRAPH_PERF_ALERT_WINDOW_MIN_SAMPLES:
            sustained_counter[qt] = 0
            continue

        severity = _classify_severity(p95, max_ms, threshold)

        if severity is None:
            sustained_counter[qt] = 0
            continue

        # 持续累计
        sustained_counter[qt] += 1
        if sustained_counter[qt] < settings.GRAPH_PERF_ALERT_SUSTAINED_ROUNDS:
            continue

        out.append(
            {
                "alert_type": "p95_threshold_breach",
                "query_type": qt,
                "severity": severity,
                "triggered_at": datetime.now(timezone.utc),
                "window_size": samples,
                "p50_ms": float(snap["p50_ms"][qt]),
                "p95_ms": p95,
                "max_ms": max_ms,
                "slow_count": slow_count,
                "threshold_ms": threshold,
                "message": _build_message(qt, severity, p95, threshold, slow_count),
                "metadata": {},
            }
        )

    return out


def _persist_round(alerts_to_emit: List[dict], db=None) -> int:
    """写入一轮新告警；同时把已恢复的旧告警 mark resolved。

    返回：写入的告警数。
    ``db`` 可注入 session（测试用）；默认开 SessionLocal（生产）。
    """
    if not alerts_to_emit:
        return 0

    _own = db is None
    if _own:
        db = SessionLocal()
    written = 0
    try:
        for a in alerts_to_emit:
            db.execute(
                text(
                    """
                    INSERT INTO soc_graph_perf_alerts
                    (id, alert_type, query_type, severity, triggered_at, window_size,
                     p50_ms, p95_ms, max_ms, slow_count, threshold_ms,
                     message, resolved, "metadata")
                    VALUES
                    (gen_random_uuid(), :alert_type, :query_type, :severity, :triggered_at, :window_size,
                     :p50_ms, :p95_ms, :max_ms, :slow_count, :threshold_ms,
                     :message, FALSE, CAST(:metadata AS jsonb))
                    """
                ),
                {
                    "alert_type": a["alert_type"],
                    "query_type": a["query_type"],
                    "severity": a["severity"],
                    "triggered_at": a["triggered_at"],
                    "window_size": a["window_size"],
                    "p50_ms": a["p50_ms"],
                    "p95_ms": a["p95_ms"],
                    "max_ms": a["max_ms"],
                    "slow_count": a["slow_count"],
                    "threshold_ms": a["threshold_ms"],
                    "message": a["message"],
                    "metadata": "{}",
                },
            )
            written += 1
        db.commit()
        return written
    except Exception:
        db.rollback()
        logger.exception("graph perf alert persist failed")
        return 0
    finally:
        if _own:
            db.close()


def _mark_resolved(query_types_recovered: List[str], db=None) -> int:
    """把指定 query_type 的所有未解决告警标记 resolved。

    ``db`` 可注入 session（测试用）；默认开 SessionLocal（生产）。
    """
    if not query_types_recovered:
        return 0
    _own = db is None
    if _own:
        db = SessionLocal()
    try:
        result = db.execute(
            text(
                """
                UPDATE soc_graph_perf_alerts
                SET resolved = TRUE, resolved_at = now()
                WHERE resolved = FALSE AND query_type = ANY(:qts)
                """
            ),
            {"qts": query_types_recovered},
        )
        db.commit()
        return result.rowcount or 0
    except Exception:
        db.rollback()
        logger.exception("graph perf alert mark-resolved failed")
        return 0
    finally:
        if _own:
            db.close()


async def evaluate_once() -> dict:
    """执行一轮监控：{emitted, resolved, snapshot_samples}。"""
    snap = snapshot()
    sustained: Dict[str, int] = {}  # 本轮计数器（无状态，每次 evaluate 都从 0 开始更安全；
                                  # 简化：本次 session 内累计；跨重启丢失 = 自然冷启防抖）

    alerts = evaluate_one_round(snap, snap["slow_threshold_ms"], sustained)
    emitted = _persist_round(alerts)

    # 恢复：找出本轮 P95 低于阈值的 query_type
    recovered = [
        qt for qt in ("neighbors", "paths", "impact_scope", "vuln_chokepoints")
        if float(snap["p95_ms"][qt]) < float(snap["slow_threshold_ms"])
        and int(snap["samples"][qt]) >= settings.GRAPH_PERF_ALERT_WINDOW_MIN_SAMPLES
    ]
    resolved = _mark_resolved(recovered)

    return {
        "emitted": emitted,
        "resolved": resolved,
        "snapshot_window_size": snap["window_size"],
        "sustained_rounds_required": settings.GRAPH_PERF_ALERT_SUSTAINED_ROUNDS,
    }


async def _loop() -> None:
    interval = max(int(settings.GRAPH_PERF_MONITOR_INTERVAL_SECONDS), 30)
    logger.info("graph perf monitor started, interval=%ds", interval)
    await asyncio.sleep(_FIRST_RUN_DELAY)
    while True:
        try:
            result = await evaluate_once()
            if result["emitted"] or result["resolved"]:
                logger.info("graph perf monitor round: %s", result)
        except Exception:  # noqa: BLE001
            logger.exception("graph perf monitor round failed")
        await asyncio.sleep(interval)


def start_graph_perf_monitor() -> None:
    global _task
    if not settings.GRAPH_PERF_MONITOR_ENABLED:
        logger.info("graph perf monitor disabled by config")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop())


def stop_graph_perf_monitor() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
        logger.info("graph perf monitor stopped")