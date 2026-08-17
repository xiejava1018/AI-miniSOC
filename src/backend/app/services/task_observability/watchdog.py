"""
看门狗：60s 一次扫 zombie / stale / self-heal。

v0.4 §3.8 关键设计：
- 自身注册为 task_key="__watchdog__" 自指（task_type=watchdog）
- 启动时 timeout_s=120 校验
- 每 tick 写 task_watchdog_alive=1 / task_watchdog_last_tick=now
- 扫 zombie：running run 且 started_at 超 2*timeout_s（无进度）或 last_progress_at 超 timeout_s（有进度）
- 扫 stale：enabled registry 且 last_run_at 超 2*expected_interval_s
- NTP 漂移 > 60s 时暂停 zombie 判定（写 task_watchdog_clock_skew_seconds）
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core import database as _db
from app.models.task_observability import SocTaskRegistry, SocTaskRun, TaskRunStatus

from . import store
from .dedup import notification_dedup
from .metrics import (
    task_consecutive_failures,
    task_staleness_seconds,
    task_success_rate_24h,
    task_watchdog_alive,
    task_watchdog_clock_skew_seconds,
    task_watchdog_last_tick,
    task_zombie_total,
)
from .notification_queue import notification_queue

logger = logging.getLogger(__name__)

WATCHDOG_TASK_KEY = "__watchdog__"
WATCHDOG_INTERVAL_S = 60
WATCHDOG_TIMEOUT_S = 120
CLOCK_SKEW_THRESHOLD_S = 60

_watchdog_task: Optional[asyncio.Task] = None
_stop_event: Optional[asyncio.Event] = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _detect_clock_skew() -> float:
    """返回 monotonic 与 wall clock 的差值秒数。

    如果 NTP 在最近发生了大跳变，monotonic - wall 差异会异常。
    这里用一个简化检测：读 PG now() 与本机 now() 对比。
    """
    try:
        db = _db.SessionLocal()
        try:
            from sqlalchemy import text
            pg_now = db.execute(text("SELECT now()")).scalar()
            if pg_now is None:
                return 0.0
            local_now = datetime.now(timezone.utc)
            if pg_now.tzinfo is None:
                pg_now = pg_now.replace(tzinfo=timezone.utc)
            return abs((local_now - pg_now).total_seconds())
        finally:
            db.close()
    except Exception:
        logger.exception("clock skew check failed")
        return 0.0


def _find_zombies(db: Session, now: datetime) -> list[SocTaskRun]:
    """v0.4 §3.8：基于 runs 行 last_progress_at 的判定（每 run 独立）。"""
    running = store.list_running_runs(db)
    zombies: list[SocTaskRun] = []
    for run in running:
        if run.task_key == WATCHDOG_TASK_KEY:
            continue  # 自身不判
        reg = db.get(SocTaskRegistry, run.task_key)
        if reg is None:
            continue
        timeout_s = max(reg.timeout_s or 360, 30)
        age_since_start = (now - run.started_at).total_seconds() if run.started_at else 0
        if run.last_progress_at is None:
            # 无进度：仅 started_at 超 2*timeout_s 才判 zombie（容忍慢启动）
            if age_since_start > 2 * timeout_s:
                zombies.append(run)
        else:
            age_since_progress = (now - run.last_progress_at).total_seconds()
            if age_since_start > 2 * timeout_s and age_since_progress > timeout_s:
                zombies.append(run)
    return zombies


def _tick_once() -> dict:
    db = _db.SessionLocal()
    zombies_found = 0
    stale_found = 0
    try:
        now = _now()

        # 1. 自身 registry
        store.upsert_registry(
            db,
            task_key=WATCHDOG_TASK_KEY,
            task_name="Task Observability Watchdog",
            task_type="watchdog",
            owner_module=__name__,
            schedule_expr=f"@every {WATCHDOG_INTERVAL_S}s",
            expected_interval_s=WATCHDOG_INTERVAL_S,
            timeout_s=WATCHDOG_TIMEOUT_S,
            enabled=True,
        )

        # 2. NTP 漂移
        skew = _detect_clock_skew()
        task_watchdog_clock_skew_seconds.set(skew)

        # 3. 扫 zombie（clock skew 大时暂停）
        if skew > CLOCK_SKEW_THRESHOLD_S:
            logger.warning(
                "clock skew %.1fs > %ds, skip zombie detection",
                skew, CLOCK_SKEW_THRESHOLD_S,
            )
        else:
            zombies = _find_zombies(db, now)
            for run in zombies:
                store.mark_zombie(
                    db, run.id,
                    reason=f"started_at={run.started_at}, last_progress_at={run.last_progress_at}",
                )
                task_zombie_total.inc()
                notification_queue.enqueue(
                    "task_zombie",
                    {
                        "task_key": run.task_key,
                        "run_id": str(run.id),
                        "status": "zombie",
                        "error_text": f"zombie detected at {now.isoformat()}",
                    },
                )
                zombies_found += 1

        # 4. 扫 stale
        stale = store.list_stale_tasks(db, now)
        for reg in stale:
            if reg.task_key == WATCHDOG_TASK_KEY:
                continue
            age = (now - (reg.last_run_at or reg.created_at)).total_seconds()
            task_staleness_seconds.labels(task_key=reg.task_key).set(age)
            if notification_dedup.should_send(
                reg.task_key, "task_staleness", f"stale_{int(age)}s"
            ):
                notification_queue.enqueue(
                    "task_staleness",
                    {
                        "task_key": reg.task_key,
                        "status": "stale",
                        "error_text": f"no run for {int(age)}s (expected ≤ {2*reg.expected_interval_s}s)",
                    },
                )
            stale_found += 1

        # 5. 更新各任务 consecutive_failures / success_rate_24h
        for reg in db.query(SocTaskRegistry).all():
            task_consecutive_failures.labels(task_key=reg.task_key).set(
                reg.consecutive_failures or 0
            )
            if reg.last_run_at:
                age = (now - reg.last_run_at).total_seconds()
                task_staleness_seconds.labels(task_key=reg.task_key).set(age)
            _update_success_rate(db, reg.task_key, now)

        # 6. 去重缓存清理
        notification_dedup.cleanup()

        # 7. 自身存活指标 + 自指 registry（让 /health 能算出 last_tick_seconds_ago）
        task_watchdog_alive.set(1)
        task_watchdog_last_tick.set(now.timestamp())
        try:
            store.upsert_registry(
                db,
                task_key=WATCHDOG_TASK_KEY,
                task_name="任务看门狗",
                task_type="watchdog",
                owner_module="app.services.task_observability.watchdog",
                schedule_expr=f"every {WATCHDOG_INTERVAL_S}s",
                expected_interval_s=WATCHDOG_INTERVAL_S * 2,
                timeout_s=120,
                enabled=True,
                last_run_at=now,
                last_status=TaskRunStatus.SUCCESS,
                last_stats={"zombies": zombies_found, "stale": stale_found, "clock_skew": skew},
            )
        except Exception:
            logger.exception("watchdog self-registry upsert failed")

        return {"zombies": zombies_found, "stale": stale_found, "clock_skew": skew}
    finally:
        db.close()


def _update_success_rate(db: Session, task_key: str, now: datetime) -> None:
    """24h 成功率：success / total。"""
    cutoff = now - timedelta(hours=24)
    rows = db.query(SocTaskRun.status).filter(
        SocTaskRun.task_key == task_key,
        SocTaskRun.started_at >= cutoff,
    ).all()
    total = len(rows)
    if total == 0:
        return
    success = sum(1 for r in rows if r[0] == TaskRunStatus.SUCCESS.value)
    task_success_rate_24h.labels(task_key=task_key).set(success / total)


async def _watchdog_loop() -> None:
    logger.info("task watchdog loop started (interval=%ds)", WATCHDOG_INTERVAL_S)
    # 启动后立即 tick 一次，避免 /health 初始 last_tick=null 与 degraded
    try:
        result = await asyncio.to_thread(_tick_once)
        if result["zombies"] or result["stale"]:
            logger.warning("watchdog initial tick: %s", result)
    except Exception:
        logger.exception("watchdog initial tick failed")

    while _stop_event is not None and not _stop_event.is_set():
        try:
            # 跑在线程池，避免 DB 阻塞 event loop
            result = await asyncio.to_thread(_tick_once)
            if result["zombies"] or result["stale"]:
                logger.warning("watchdog tick: %s", result)
            else:
                logger.debug("watchdog tick: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("watchdog tick failed")
            task_watchdog_alive.set(0)
        try:
            await asyncio.wait_for(
                _stop_event.wait(), timeout=WATCHDOG_INTERVAL_S
            )
        except asyncio.TimeoutError:
            pass
    logger.info("task watchdog loop stopped")


def start_watchdog() -> None:
    global _watchdog_task, _stop_event
    if _watchdog_task is not None and not _watchdog_task.done():
        return
    _stop_event = asyncio.Event()
    _watchdog_task = asyncio.create_task(_watchdog_loop())
    logger.info("task watchdog started")


async def stop_watchdog() -> None:
    global _watchdog_task, _stop_event
    if _stop_event is not None:
        _stop_event.set()
    if _watchdog_task is not None:
        _watchdog_task.cancel()
        try:
            await _watchdog_task
        except (asyncio.CancelledError, Exception):
            pass
    _watchdog_task = None
    task_watchdog_alive.set(0)
    logger.info("task watchdog stopped")
