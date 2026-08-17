"""
任务 handler 注册中心。

@track_task 装饰器在被装饰函数首次定义时自动把 wrapper 注册到这里。
trigger API 通过 task_key 查找对应 handler 并异步执行。
"""
from __future__ import annotations

import logging
from typing import Awaitable, Callable, Dict, Optional

logger = logging.getLogger(__name__)

# task_key -> 被 @track_task 包装后的 async 函数
_HANDLERS: Dict[str, Callable[..., Awaitable]] = {}


def register_handler(task_key: str, handler: Callable[..., Awaitable]) -> None:
    if task_key in _HANDLERS and _HANDLERS[task_key] is not handler:
        logger.warning("handler for %s replaced", task_key)
    _HANDLERS[task_key] = handler


def get_handler(task_key: str) -> Optional[Callable[..., Awaitable]]:
    return _HANDLERS.get(task_key)


def all_handlers() -> Dict[str, Callable[..., Awaitable]]:
    return dict(_HANDLERS)


def register_all_handlers_now() -> int:
    """启动时调一次：让所有 @track_task 装饰过的函数立即写 registry。
    
    否则要等到每个 scheduler 首次 tick 才会 upsert（可能要几小时甚至次日）。
    调用每个 handler 的 _task_meta 不执行 body。
    """
    from app.core import database as _db
    from . import store

    count = 0
    for task_key, handler in list(_HANDLERS.items()):
        meta = getattr(handler, "_task_meta", None)
        if not meta:
            continue
        db = _db.SessionLocal()
        try:
            store.upsert_registry(
                db,
                task_key=task_key,
                task_name=meta["task_name"],
                task_type=meta["task_type"],
                owner_module=meta["owner_module"],
                schedule_expr=meta["schedule_expr"],
                expected_interval_s=meta["expected_interval_s"],
                timeout_s=max(30, meta["timeout_s"]),  # 防御：过小的值夹紧到 30
            )
            count += 1
        except Exception:
            logging.getLogger(__name__).exception(
                "register handler failed for %s (skipping)", task_key
            )
        finally:
            db.close()
    return count
