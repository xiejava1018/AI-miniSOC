"""
线程型后台任务的心跳上报（v0.4.2 Phase 2.1）

适用场景：
- threading.Thread + 固定 tick 间隔的循环（如 MCP token refresher）
- 不适合 @track_task（每 tick 都写 run 表会产生海量无意义记录）
- 真正做事时才写一条 run 记录（如 token 真的刷新了 / 刷新失败了）

使用方式：
    from app.services.task_observability.heartbeat import ThreadHeartbeat

    hb = ThreadHeartbeat(
        task_key="mcp_token_refresher",
        task_name="MCP Token 刷新",
        interval_s=60,
        timeout_s=600,
    )
    hb.register()  # 启动时注册 registry

    while not stop.is_set():
        hb.tick()  # 每 tick 上报心跳（只更新 last_run_at，不写 run 表）
        try:
            if need_refresh:
                hb.run_started()
                do_refresh()
                hb.run_succeeded(stats={"refreshed": True})
        except Exception as e:
            hb.run_failed(error=e)
        stop.wait(60)

    hb.unregister()
"""
from __future__ import annotations

import logging
import time
import uuid  # noqa: F401  (供未来扩展使用)
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Optional

from app.core import database as _db
from app.models.task_observability import TaskRunStatus

from . import store
from .metrics import (
    task_consecutive_failures,
    task_last_duration_seconds,
    task_runs_total,
)
from .notification_queue import notification_queue

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ThreadHeartbeat:
    """线程型任务的轻量观测器。

    - register()：写入/更新 soc_task_registry
    - tick()：更新 last_run_at（仅 heartbeat，不写 run 表）
    - run_started()/run_succeeded()/run_failed()：真正执行一次工作时写 run 记录
    - @contextmanager run()：with hb.run(): ... 自动处理成功/失败
    """

    def __init__(
        self,
        *,
        task_key: str,
        task_name: str,
        owner_module: str,
        interval_s: int,
        timeout_s: int = 600,
        schedule_expr: Optional[str] = None,
    ):
        self.task_key = task_key
        self.task_name = task_name
        self.owner_module = owner_module
        self.interval_s = interval_s
        self.timeout_s = max(30, timeout_s)
        self.schedule_expr = schedule_expr or f"every {interval_s}s (thread)"
        self._current_run_id: Optional[str] = None
        self._current_run_started: Optional[float] = None

    # ------------------------------------------------------------ registry
    def register(self) -> None:
        """启动时注册任务元数据。"""
        db = _db.SessionLocal()
        try:
            store.upsert_registry(
                db,
                task_key=self.task_key,
                task_name=self.task_name,
                task_type="thread",
                owner_module=self.owner_module,
                schedule_expr=self.schedule_expr,
                expected_interval_s=self.interval_s * 3,  # 3 个 tick 没心跳算 stale
                timeout_s=self.timeout_s,
                enabled=True,
                last_run_at=_now(),
                last_status=TaskRunStatus.SUCCESS,
                last_stats={"heartbeat": "registered"},
            )
        except Exception:
            logger.exception(
                "heartbeat: register failed for %s", self.task_key
            )
        finally:
            db.close()

    def unregister(self) -> None:
        """应用关闭时标记禁用（可选）。"""
        # 当前实现不删除 registry，只更新 last_status
        db = _db.SessionLocal()
        try:
            store.upsert_registry(
                db,
                task_key=self.task_key,
                task_name=self.task_name,
                task_type="thread",
                owner_module=self.owner_module,
                schedule_expr=self.schedule_expr,
                expected_interval_s=self.interval_s * 3,
                timeout_s=self.timeout_s,
                enabled=False,
                last_run_at=_now(),
                last_status=TaskRunStatus.UNKNOWN,
                last_stats={"reason": "shutdown"},
            )
        except Exception:
            logger.exception(
                "heartbeat: unregister failed for %s", self.task_key
            )
        finally:
            db.close()

    # ------------------------------------------------------------ heartbeat
    def tick(self, stats: Optional[dict] = None) -> None:
        """每轮循环调一次，更新 last_run_at 让 watchdog 知道还活着。

        不写 soc_task_runs 表（避免每 60s 一条空记录）。
        """
        db = _db.SessionLocal()
        try:
            store.upsert_registry(
                db,
                task_key=self.task_key,
                task_name=self.task_name,
                task_type="thread",
                owner_module=self.owner_module,
                schedule_expr=self.schedule_expr,
                expected_interval_s=self.interval_s * 3,
                timeout_s=self.timeout_s,
                enabled=True,
                last_run_at=_now(),
                last_stats=stats or {"heartbeat": "tick"},
            )
        except Exception:
            logger.warning(
                "heartbeat: tick failed for %s", self.task_key, exc_info=True
            )
        finally:
            db.close()

    # ------------------------------------------------------------ run 记录
    def run_started(self, trigger: str = "scheduled") -> str:
        """标记一次真正的工作开始。返回 run_id。"""
        self._current_run_started = time.time()
        db = _db.SessionLocal()
        try:
            run = store.create_run(
                db,
                task_key=self.task_key,
                trigger=trigger,
            )
            self._current_run_id = str(run.id)
            return self._current_run_id
        except Exception:
            logger.exception(
                "heartbeat: run_started failed for %s", self.task_key
            )
            self._current_run_id = None
            return ""
        finally:
            db.close()

    def _get_registry(self, db):
        return db.get(
            __import__(
                "app.models.task_observability", fromlist=["SocTaskRegistry"]
            ).SocTaskRegistry,
            self.task_key,
        )

    def run_succeeded(
        self,
        stats: Optional[dict] = None,
        trigger: str = "scheduled",
    ) -> None:
        """标记当前工作成功完成。"""
        if not self._current_run_id:
            # 可能没调 run_started，直接补一条
            self.run_started(trigger=trigger)
        duration_ms = None
        if self._current_run_started:
            duration_ms = int((time.time() - self._current_run_started) * 1000)
        db = _db.SessionLocal()
        try:
            import uuid as _uuid
            store.finish_run(
                db,
                run_id=_uuid.UUID(self._current_run_id),
                status=TaskRunStatus.SUCCESS,
                stats={"duration_ms": duration_ms, **(stats or {})},
            )
            task_runs_total.labels(
                task_key=self.task_key, status="success", trigger=trigger
            ).inc()
            if duration_ms is not None:
                task_last_duration_seconds.labels(task_key=self.task_key).set(
                    duration_ms / 1000
                )
            task_consecutive_failures.labels(task_key=self.task_key).set(0)
        except Exception:
            logger.exception(
                "heartbeat: run_succeeded failed for %s", self.task_key
            )
        finally:
            db.close()
            self._current_run_id = None
            self._current_run_started = None

    def run_failed(
        self,
        error: BaseException,
        stats: Optional[dict] = None,
        trigger: str = "scheduled",
        notify: bool = True,
    ) -> None:
        """标记当前工作失败。notify=True 时投递告警通知。"""
        if not self._current_run_id:
            self.run_started(trigger=trigger)
        duration_ms = None
        if self._current_run_started:
            duration_ms = int((time.time() - self._current_run_started) * 1000)
        error_text = f"{type(error).__name__}: {error}"[:2000]

        db = _db.SessionLocal()
        try:
            import uuid as _uuid
            from app.models.task_observability import SocTaskRegistry
            store.finish_run(
                db,
                run_id=_uuid.UUID(self._current_run_id),
                status=TaskRunStatus.FAILED,
                error_text=error_text,
                stats={"duration_ms": duration_ms, **(stats or {})},
            )
            reg = db.get(SocTaskRegistry, self.task_key)
            task_runs_total.labels(
                task_key=self.task_key, status="failed", trigger=trigger
            ).inc()
            task_consecutive_failures.labels(task_key=self.task_key).set(
                (reg.consecutive_failures if reg else 0) or 0
            )

            # 连续失败 3 次才通知（避免抖动）
            if notify and reg and (reg.consecutive_failures or 0) >= 3:
                notification_queue.enqueue(
                    "task_failure",
                    {
                        "task_key": self.task_key,
                        "task_name": self.task_name,
                        "run_id": self._current_run_id,
                        "status": "failed",
                        "error_text": error_text,
                        "consecutive_failures": reg.consecutive_failures,
                    },
                )
        except Exception:
            logger.exception(
                "heartbeat: run_failed failed for %s", self.task_key
            )
        finally:
            db.close()
            self._current_run_id = None
            self._current_run_started = None

    @contextmanager
    def run(self, trigger: str = "scheduled", notify_on_failure: bool = True):
        """with 语法：

            with hb.run():
                do_work()
        """
        self.run_started(trigger=trigger)
        try:
            yield self._current_run_id
        except Exception as e:
            self.run_failed(e, trigger=trigger, notify=notify_on_failure)
            raise
        else:
            self.run_succeeded(trigger=trigger)
