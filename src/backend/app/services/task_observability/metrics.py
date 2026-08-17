"""
Prometheus 指标（task observability 7 个）。

参考设计文档 v0.4.2 §3.12：
- task_runs_total{task_key,status,trigger}  Counter
- task_last_duration_seconds{task_key}      Gauge
- task_consecutive_failures{task_key}       Gauge
- task_staleness_seconds{task_key}          Gauge
- task_zombie_total                          Gauge
- task_watchdog_alive                        Gauge
- task_success_rate_24h{task_key}           Gauge
- task_watchdog_last_tick                    Gauge (epoch seconds)
- task_watchdog_clock_skew_seconds           Gauge
- notification_dropped_total{reason}         Counter
"""
from __future__ import annotations

from prometheus_client import Counter, Gauge

task_runs_total = Counter(
    "task_runs_total",
    "Task run count by task_key, status, trigger",
    ["task_key", "status", "trigger"],
)

task_last_duration_seconds = Gauge(
    "task_last_duration_seconds",
    "Last run duration in seconds",
    ["task_key"],
)

task_consecutive_failures = Gauge(
    "task_consecutive_failures",
    "Consecutive failures for task",
    ["task_key"],
)

task_staleness_seconds = Gauge(
    "task_staleness_seconds",
    "Seconds since last success for task",
    ["task_key"],
)

task_zombie_total = Gauge(
    "task_zombie_total",
    "Total zombie runs currently flagged",
)

task_watchdog_alive = Gauge(
    "task_watchdog_alive",
    "1 if watchdog loop ran within last 2 minutes, else 0",
)

task_watchdog_last_tick = Gauge(
    "task_watchdog_last_tick",
    "Epoch timestamp of last watchdog tick",
)

task_watchdog_clock_skew_seconds = Gauge(
    "task_watchdog_clock_skew_seconds",
    "Clock skew detected by NTP drift check (0 if none)",
)

task_success_rate_24h = Gauge(
    "task_success_rate_24h",
    "24h rolling success rate (0-1) per task",
    ["task_key"],
)

notification_dropped_total = Counter(
    "notification_dropped_total",
    "Notifications dropped by reason (dedup, no_recipients, all_failed, queue_full)",
    ["reason"],
)
