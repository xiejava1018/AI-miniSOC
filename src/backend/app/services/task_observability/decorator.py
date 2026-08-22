"""
@track_task 装饰器（POC-2 正确模式）。

关键：sync body 必须包在 to_thread 里，装饰器内部：
    inner_task = asyncio.create_task(asyncio.to_thread(body))
    try:
        async with asyncio.timeout(timeout_s):
            await asyncio.shield(inner_task)
    except TimeoutError:
        await inner_task  # 等同步线程跑完，锁不释放

这样：
- 业务超过 timeout_s 立即返回 status=timeout
- 但锁持有到同步线程真正结束，防止 PG 并发查询翻倍
- 期间所有 tick / trigger 看到 lock.locked()=True → 写 skipped run
"""
from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from app.core import database as _db
from app.models.task_observability import TaskRunStatus
from app.services.source_health import SourceHealthRecorder

from . import store
from .handlers import register_handler
from .lock import get_task_lock
from .metrics import (
    task_consecutive_failures,
    task_last_duration_seconds,
    task_runs_total,
)
from .notification_queue import notification_queue

logger = logging.getLogger(__name__)

# 生产环境 timeout_s 最小 30s（防 P0-4 配置错误造成误报 zombie）。
# 测试时可设为 0 来放开，验证 1s timeout 行为。
MIN_TIMEOUT_S = 30


# ContextVar：让 body 内部能拿到 run_id / 调进度更新
_current_run_id: ContextVar[Optional[uuid.UUID]] = ContextVar("current_run_id", default=None)
_current_task_key: ContextVar[Optional[str]] = ContextVar("current_task_key", default=None)

# 进度上报节流：run_id -> 上次写入 monotonic timestamp
# 设计取舍：用 dict 而非 ContextVar，因为 run_id 唯一且任务并发数少
_last_progress_ts: dict = {}


def current_run_id() -> Optional[uuid.UUID]:
    return _current_run_id.get()


def current_task_key() -> Optional[str]:
    return _current_task_key.get()


def update_progress(
    *,
    processed: Optional[int] = None,
    total: Optional[int] = None,
    percent: Optional[int] = None,
    stats: Optional[dict] = None,
) -> bool:
    """模块级进度上报便捷函数（Phase 2.4）。

    在被 @track_task 装饰的函数体内任意位置调用，
    通过 ContextVar 拿到当前 run_id 并写库。

    与 ctx.update_progress() 二选一：
      - 接受 ctx 参数的函数：用 ctx.update_progress()（避免 ContextVar 查找）
      - 不想改签名的函数：直接调本函数

    Returns:
        True 如果成功写入，False 如果不在 task 上下文中（静默 no-op）。

    节流：内部限制最多每 2 秒写一次库，避免高频循环压垮 DB。
    """
    run_id = _current_run_id.get()
    if run_id is None:
        return False
    # 节流：同一 run 2s 内多次调用只写一次
    now = time.monotonic()
    last = _last_progress_ts.get(run_id, 0)
    if now - last < 2.0 and processed is not None and total is not None:
        # 未到 2s，只在 100% 时强制写
        if processed < total:
            return False
    _last_progress_ts[run_id] = now
    # 自动算 percent（调用方只给 processed/total 也能落库完整进度）
    if percent is None and processed is not None and total is not None and total > 0:
        percent = min(100, round(processed / total * 100))
    db = _db.SessionLocal()
    try:
        store.update_run_progress(
            db,
            run_id,
            processed=processed,
            total=total,
            percent=percent,
            stats=stats,
        )
        return True
    except Exception:
        logger.warning("update_progress failed for run %s", run_id, exc_info=True)
        return False
    finally:
        db.close()


def update_progress_stage(
    stage: str,
    *,
    processed: Optional[int] = None,
    total: Optional[int] = None,
    percent: Optional[int] = None,
    extra: Optional[dict] = None,
) -> bool:
    """阶段式进度：合并 stage 名到 stats。

    例：
        update_progress_stage("fetch", total=100)
        update_progress_stage("parse", processed=50, total=100)
        update_progress_stage("commit", processed=100, total=100)
    """
    stats = {"stage": stage}
    if extra:
        stats.update(extra)
    return update_progress(
        processed=processed, total=total, percent=percent, stats=stats
    )


@dataclass
class TrackTaskContext:
    """传给 body 的 ctx 对象（仅当 body 声明接受 ctx 参数时）。"""

    task_key: str
    run_id: uuid.UUID
    started_at: float
    _progress_written: bool = field(default=False)

    def update_progress(
        self,
        *,
        processed: Optional[int] = None,
        total: Optional[int] = None,
        percent: Optional[int] = None,
        stats: Optional[dict] = None,
    ) -> None:
        db = _db.SessionLocal()
        try:
            store.update_run_progress(
                db,
                self.run_id,
                processed=processed,
                total=total,
                percent=percent,
                stats=stats,
            )
            self._progress_written = True
        finally:
            db.close()


def track_task(
    *,
    task_key: str,
    task_name: Optional[str] = None,
    task_type: str = "scheduled",
    owner_module: Optional[str] = None,
    schedule_expr: Optional[str] = None,
    expected_interval_s: Optional[int] = None,
    timeout_s: int = 360,
    source_key: Optional[str] = None,
    register_on_call: bool = True,
) -> Callable:
    """装饰一个 async 函数，给它加上任务追踪、锁、超时、指标。

    被装饰函数可以：
    - 是 async def（协程主体用 asyncio.to_thread 跑同步 DB）
    - 接受可选的 ctx: TrackTaskContext 参数（用于进度上报）
    - 返回任意 dict / pydantic 模型，dict 会作为 stats_json 落库

    用法：
        @track_task(task_key="browsing_detector", timeout_s=600, source_key="loki:browsing")
        async def run_detection_once(): ...
    """
    if timeout_s < MIN_TIMEOUT_S:
        raise ValueError(f"timeout_s must be >= {MIN_TIMEOUT_S}, got {timeout_s}")

    def decorator(func: Callable) -> Callable:
        # 自动注册用的元数据
        func._task_meta = {  # type: ignore[attr-defined]
            "task_key": task_key,
            "task_name": task_name or func.__name__,
            "task_type": task_type,
            "owner_module": owner_module or func.__module__,
            "schedule_expr": schedule_expr,
            "expected_interval_s": expected_interval_s,
            "timeout_s": timeout_s,
        }

        @functools.wraps(func)
        async def wrapper(*args, trigger: str = "scheduled", **kwargs) -> Any:
            meta = func._task_meta  # type: ignore[attr-defined]

            # 1. 启动时幂等注册（每次都 upsert，保证 schema 漂移后仍能自愈）
            if register_on_call:
                try:
                    db = _db.SessionLocal()
                    try:
                        store.upsert_registry(
                            db,
                            task_key=meta["task_key"],
                            task_name=meta["task_name"],
                            task_type=meta["task_type"],
                            owner_module=meta["owner_module"],
                            schedule_expr=meta["schedule_expr"],
                            expected_interval_s=meta["expected_interval_s"],
                            timeout_s=meta["timeout_s"],
                        )
                    finally:
                        db.close()
                except Exception:
                    logger.exception("upsert_registry failed for %s", task_key)

            # 2. 防重叠：拿进程内锁
            lock = get_task_lock(task_key)
            if lock.locked():
                # 上一轮还在跑（可能 in-flight trigger，也可能 timeout 等同步线程）
                _record_skip(
                    task_key=task_key,
                    trigger=trigger,
                    reason="lock held (previous run still in flight)",
                )
                return None

            async with lock:
                db = _db.SessionLocal()
                try:
                    run = store.create_run(
                        db,
                        task_key=task_key,
                        trigger=trigger,
                    )
                finally:
                    db.close()

                t0 = time.monotonic()
                status = TaskRunStatus.SUCCESS
                error_text: Optional[str] = None
                result: Any = None

                # 准备 ctx（如果 body 接受）
                ctx = TrackTaskContext(
                    task_key=task_key, run_id=run.id, started_at=t0
                )
                want_ctx = _func_wants_ctx(func)

                # 设置 ContextVar
                token_rid = _current_run_id.set(run.id)
                token_key = _current_task_key.set(task_key)

                try:
                    # ★ POC-2 正确模式：create_task + shield + 显式 await
                    async def _invoke() -> Any:
                        if want_ctx:
                            return await func(*args, ctx=ctx, **kwargs)
                        return await func(*args, **kwargs)

                    inner_task = asyncio.create_task(_invoke())
                    try:
                        async with asyncio.timeout(timeout_s):
                            result = await asyncio.shield(inner_task)
                        status = TaskRunStatus.SUCCESS
                    except TimeoutError:
                        logger.warning(
                            "task %s run %s TIMEOUT after %ds, waiting for orphan thread...",
                            task_key, run.id, timeout_s,
                        )
                        # 等同步线程跑完——锁不释放，下一轮 tick 会看到 lock.locked()=True
                        try:
                            result = await inner_task
                            # 跑完了——业务超过 timeout_s 但代码最终完成
                            status = TaskRunStatus.TIMEOUT
                            error_text = f"exceeded timeout_s={timeout_s}s but body completed"
                        except Exception as inner_e:
                            status = TaskRunStatus.FAILED
                            error_text = f"after timeout: {type(inner_e).__name__}: {inner_e}"
                            logger.exception("task %s orphan body raised", task_key)
                    except asyncio.CancelledError:
                        # 外层 cancel（应用 shutdown / trigger cancel）——尽力等 inner
                        logger.warning("task %s run %s CANCELLED", task_key, run.id)
                        try:
                            await asyncio.shield(inner_task)
                        except Exception:  # noqa: BLE001
                            pass
                        status = TaskRunStatus.FAILED
                        error_text = "cancelled"
                        raise
                except Exception as e:  # body 自身抛错
                    status = TaskRunStatus.FAILED
                    error_text = f"{type(e).__name__}: {e}"
                    logger.exception("task %s run %s FAILED", task_key, run.id)
                    body_exc = e  # 记下，后面重新 raise
                else:
                    body_exc = None
                finally:
                    _current_run_id.reset(token_rid)
                    _current_task_key.reset(token_key)
                    # 清理进度节流缓存
                    _last_progress_ts.pop(run.id, None)

                duration_s = time.monotonic() - t0
                stats = _extract_stats(result)

                db = _db.SessionLocal()
                try:
                    store.finish_run(
                        db,
                        run.id,
                        status,
                        error_text=error_text,
                        stats=stats,
                    )
                    # 数据源健康（P4 WO-2：修成功路径构造错误 + 补失败路径）
                    # v1.0 文档以为成功路径已生效——实测 SourceHealthRecorder(db)
                    # 构造器要求 db，原代码传 source_key 会 TypeError，被下面
                    # except 静默吞掉，即成功上报从未真正写入。此处一并修正。
                    if source_key:
                        try:
                            recorder = SourceHealthRecorder(db)
                            src_type = (
                                source_key.split(":", 1)[0] if ":" in source_key else "unknown"
                            )
                            if status == TaskRunStatus.SUCCESS:
                                recorder.record_success(
                                    source_key,
                                    source_type=src_type,
                                    records_count=(stats or {}).get("processed"),
                                )
                            else:
                                recorder.record_failure(
                                    source_key,
                                    source_type=src_type,
                                    error=error_text or status.value,
                                )
                            db.commit()
                        except Exception:
                            db.rollback()
                            logger.debug("source_health record failed", exc_info=True)
                finally:
                    db.close()

                # 指标
                task_runs_total.labels(
                    task_key=task_key, status=status.value, trigger=trigger
                ).inc()
                task_last_duration_seconds.labels(task_key=task_key).set(duration_s)
                if status in (TaskRunStatus.FAILED, TaskRunStatus.TIMEOUT, TaskRunStatus.ZOMBIE):
                    task_consecutive_failures.labels(task_key=task_key).inc()
                    # 入通知队列（drain task 负责真正发送）
                    try:
                        notification_queue.enqueue(
                            "task_failure",
                            {
                                "task_key": task_key,
                                "run_id": str(run.id),
                                "status": status.value,
                                "error_text": error_text or "",
                                "duration_s": round(duration_s, 2),
                            },
                        )
                    except Exception:
                        logger.exception("enqueue notification failed")
                elif status == TaskRunStatus.SUCCESS:
                    task_consecutive_failures.labels(task_key=task_key).set(0)

                # 重新抛出 body 异常（让调度器 / trigger API 知道失败）
                if body_exc is not None:
                    raise body_exc
                return result

        wrapper._task_meta = func._task_meta  # type: ignore[attr-defined]
        # 暴露内部 func 给 scheduler 原始调用路径（避免重复包装）
        wrapper.__wrapped_func__ = func  # type: ignore[attr-defined]
        # 自动注册到 handler 中心，trigger API 可查找
        register_handler(task_key, wrapper)
        return wrapper

    return decorator


def _func_wants_ctx(func: Callable) -> bool:
    """检测被装饰函数是否声明了 ctx 参数。"""
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    return "ctx" in sig.parameters


def _extract_stats(result: Any) -> Optional[dict]:
    if result is None:
        return None
    if isinstance(result, dict):
        return result
    # pydantic model
    if hasattr(result, "model_dump"):
        try:
            return result.model_dump(mode="json")
        except Exception:
            return None
    return None


def _record_skip(task_key: str, trigger: str, reason: str) -> None:
    """拿不到锁时写一行 skipped run + 指标，不阻塞调用方。"""
    try:
        db = _db.SessionLocal()
        try:
            run = store.create_run(db, task_key=task_key, trigger=trigger)
            store.finish_run(
                db,
                run.id,
                TaskRunStatus.SKIPPED,
                error_text=reason,
            )
        finally:
            db.close()
        task_runs_total.labels(
            task_key=task_key, status=TaskRunStatus.SKIPPED.value, trigger=trigger
        ).inc()
    except Exception:
        logger.exception("record skip failed for %s", task_key)
