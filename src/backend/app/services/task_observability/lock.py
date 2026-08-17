"""
单 worker 进程内任务锁。

v0.4.1：代码已证实当前部署为单 worker（main.py check_single_worker_or_warn + 无 --workers）。
单 worker 下防 tick × manual trigger 重叠只需进程内 asyncio.Lock（最小正确解）。

Phase 2 升级多 pod 时，把 get_task_lock 改为 soc_scheduler_lease 分布式锁即可，
装饰器 body 不变。接口：
    lock = get_task_lock(task_key)
    if lock.locked(): return skipped
    async with lock: ...
"""
from __future__ import annotations

import asyncio
from typing import Dict

_task_locks: Dict[str, asyncio.Lock] = {}


def get_task_lock(task_key: str) -> asyncio.Lock:
    """返回该 task_key 专属的进程内 asyncio.Lock（不存在则创建）。

    字典的 get/set 在 CPython 下是 GIL 保护的原子操作，并发首次访问不会产生两把锁。
    """
    lock = _task_locks.get(task_key)
    if lock is None:
        lock = asyncio.Lock()
        _task_locks[task_key] = lock
    return lock
