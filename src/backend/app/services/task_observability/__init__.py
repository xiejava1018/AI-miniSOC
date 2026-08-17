"""
后台任务可观测性 v0.4.2

子模块：
- lock: 单 worker 进程内 asyncio.Lock（Phase 2 多 pod 时换分布式锁）
- store: SocTaskRegistry / SocTaskRun 读写封装
- decorator: @track_task 装饰器（POC-2 正确模式：create_task + shield + await inner）
- watchdog: 60s tick 看门狗（自指 + zombie 扫描 + stale 检测）
- metrics: Prometheus 7 个指标
- notification_queue: 无锁 deque 通知队列（POC-3）+ drain task
- dedup: 5min 滑动窗口去重
- bootstrap: lifespan 集成（启动对账 + 启动顺序）
"""
from __future__ import annotations

from .lock import get_task_lock
from .store import (
    create_run,
    finish_run,
    update_run_progress,
    upsert_registry,
    get_registry,
    list_running_runs,
    list_stale_tasks,
    reconcile_on_startup,
)
from .decorator import track_task, TrackTaskContext, update_progress, update_progress_stage, current_run_id, current_task_key
from .watchdog import start_watchdog, stop_watchdog
from .notification_queue import notification_queue, start_notification_drain, stop_notification_drain
from .dedup import notification_dedup
from .bootstrap import bootstrap_task_observability, shutdown_task_observability

__all__ = [
    "get_task_lock",
    "create_run",
    "finish_run",
    "update_run_progress",
    "upsert_registry",
    "get_registry",
    "list_running_runs",
    "list_stale_tasks",
    "reconcile_on_startup",
    "track_task",
    "TrackTaskContext",
    "update_progress",
    "update_progress_stage",
    "current_run_id",
    "current_task_key",
    "start_watchdog",
    "stop_watchdog",
    "notification_queue",
    "start_notification_drain",
    "stop_notification_drain",
    "notification_dedup",
    "bootstrap_task_observability",
    "shutdown_task_observability",
]
