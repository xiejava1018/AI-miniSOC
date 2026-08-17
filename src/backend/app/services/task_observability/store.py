"""
SocTaskRegistry / SocTaskRun 的读写封装。

所有函数都接受同步 Session（Phase 1 单 worker + 同步 SQLAlchemy）。
调用方负责 session 生命周期。
"""
from __future__ import annotations

import logging
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, select, text
from sqlalchemy.orm import Session

from app.core import database as _db
from app.models.task_observability import SocTaskRegistry, SocTaskRun, TaskRunStatus

logger = logging.getLogger(__name__)


def _session():
    """开一个新 Session。

    这一层间接让测试可以 monkeypatch ``app.core.database.SessionLocal``
    为 TestingSessionLocal，从而所有写入走测试库。
    """
    return _db.SessionLocal()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _host() -> str:
    try:
        return f"{socket.gethostname()}"
    except Exception:
        return "unknown"


# ---------------------------------------------------------------- Registry upsert

def upsert_registry(
    db: Session,
    *,
    task_key: str,
    task_name: str,
    task_type: str,
    owner_module: Optional[str] = None,
    schedule_expr: Optional[str] = None,
    expected_interval_s: Optional[int] = None,
    timeout_s: int = 360,
    enabled: bool = True,
    last_run_at: Optional[datetime] = None,
    last_status: Optional[TaskRunStatus] = None,
    last_stats: Optional[dict] = None,
) -> SocTaskRegistry:
    """注册/更新任务定义。启动时每个 scheduler 调一次。"""
    if timeout_s < 30:
        # 防御：P0-4（SRE）——timeout 过小会导致僵尸误判
        # 注：装饰器层有 MIN_TIMEOUT_S 可在测试时调小；store 层始终保护生产库
        raise ValueError(f"timeout_s must be >= 30, got {timeout_s}")

    reg = db.get(SocTaskRegistry, task_key)
    if reg is None:
        reg = SocTaskRegistry(
            task_key=task_key,
            task_name=task_name,
            task_type=task_type,
            owner_module=owner_module,
            schedule_expr=schedule_expr,
            expected_interval_s=expected_interval_s,
            timeout_s=timeout_s,
            enabled=enabled,
        )
        db.add(reg)
    else:
        # 只在显式提供时更新定义字段，避免运行时覆盖
        reg.task_name = task_name
        reg.task_type = task_type
        if owner_module is not None:
            reg.owner_module = owner_module
        if schedule_expr is not None:
            reg.schedule_expr = schedule_expr
        if expected_interval_s is not None:
            reg.expected_interval_s = expected_interval_s
        reg.timeout_s = timeout_s
        # enabled 不在这里改——由 toggle API 改

    # 运行时字段（watchdog 等会传）
    if last_run_at is not None:
        reg.last_run_at = last_run_at
    if last_status is not None:
        reg.last_status = last_status
    if last_stats is not None:
        reg.last_stats = last_stats

    db.commit()
    db.refresh(reg)
    return reg


def get_registry(db: Session, task_key: str) -> Optional[SocTaskRegistry]:
    return db.get(SocTaskRegistry, task_key)


# ---------------------------------------------------------------- Run 写入

def create_run(
    db: Session,
    *,
    task_key: str,
    trigger: str = "scheduled",
    correlation_id: Optional[str] = None,
    triggered_by_user: Optional[str] = None,
) -> SocTaskRun:
    """创建一行 status=running 的 run。"""
    run = SocTaskRun(
        id=uuid.uuid4(),
        task_key=task_key,
        trigger=trigger,
        status=TaskRunStatus.RUNNING,
        started_at=_now(),
        correlation_id=correlation_id,
        host=_host(),
        triggered_by_user=triggered_by_user,
    )
    db.add(run)
    db.flush()  # 拿 id

    # 同步更新 registry
    reg = db.get(SocTaskRegistry, task_key)
    if reg is not None:
        reg.current_run_id = run.id
        reg.lock_owner = _host()
        reg.last_run_at = run.started_at
        reg.last_status = TaskRunStatus.RUNNING
        reg.total_runs = (reg.total_runs or 0) + 1
    db.commit()
    db.refresh(run)
    return run


def update_run_progress(
    db: Session,
    run_id: uuid.UUID,
    *,
    processed: Optional[int] = None,
    total: Optional[int] = None,
    percent: Optional[int] = None,
    stats: Optional[dict] = None,
) -> None:
    """长任务进度心跳。看门狗据此区分'真卡死'和'慢但活着'。"""
    run = db.get(SocTaskRun, run_id)
    if run is None or run.status != TaskRunStatus.RUNNING:
        return
    if processed is not None:
        run.processed = processed
    if total is not None:
        run.total = total
    if percent is not None:
        run.percent = percent
    if stats is not None:
        run.stats_json = stats
    run.last_progress_at = _now()
    db.commit()


def finish_run(
    db: Session,
    run_id: uuid.UUID,
    status: TaskRunStatus,
    *,
    error_text: Optional[str] = None,
    stats: Optional[dict] = None,
) -> None:
    """结束一个 run 并同步更新 registry 状态。"""
    now = _now()
    run = db.get(SocTaskRun, run_id)
    if run is None:
        logger.warning("finish_run: run %s not found", run_id)
        return

    run.status = status
    run.finished_at = now
    if run.started_at is not None:
        run.duration_ms = int((now - run.started_at).total_seconds() * 1000)
    if error_text is not None:
        run.error_text = error_text[:4000] if error_text else None
    if stats is not None:
        run.stats_json = stats

    reg = db.get(SocTaskRegistry, run.task_key)
    if reg is not None:
        reg.current_run_id = None
        reg.lock_owner = None
        reg.last_status = status
        reg.last_run_at = now
        reg.last_duration_ms = run.duration_ms
        reg.last_stats = stats
        reg.last_error = error_text
        if status in (TaskRunStatus.SUCCESS, TaskRunStatus.SKIPPED):
            if status == TaskRunStatus.SUCCESS:
                reg.consecutive_failures = 0
        elif status in (TaskRunStatus.FAILED, TaskRunStatus.TIMEOUT, TaskRunStatus.ZOMBIE):
            reg.consecutive_failures = (reg.consecutive_failures or 0) + 1
        # SKIPPED 不计失败也不清零

    db.commit()


# ---------------------------------------------------------------- Watchdog 查询

def list_running_runs(db: Session) -> list[SocTaskRun]:
    """列出所有 status=running 的 run（partial index 加速）。"""
    return list(
        db.execute(
            select(SocTaskRun).where(SocTaskRun.status == TaskRunStatus.RUNNING)
        ).scalars()
    )


def list_stale_tasks(db: Session, now: Optional[datetime] = None) -> list[SocTaskRegistry]:
    """返回 last_run_at 超过 2×expected_interval_s 的任务。"""
    now = now or _now()
    rows = db.execute(
        select(SocTaskRegistry).where(
            and_(
                SocTaskRegistry.enabled.is_(True),
                SocTaskRegistry.expected_interval_s.isnot(None),
                SocTaskRegistry.expected_interval_s > 0,
            )
        )
    ).scalars().all()
    stale: list[SocTaskRegistry] = []
    for reg in rows:
        ref = reg.last_run_at or reg.created_at
        if ref is None:
            continue
        if now - ref > timedelta(seconds=2 * reg.expected_interval_s):
            stale.append(reg)
    return stale


def mark_zombie(db: Session, run_id: uuid.UUID, reason: str) -> None:
    run = db.get(SocTaskRun, run_id)
    if run is None or run.status != TaskRunStatus.RUNNING:
        return
    run.status = TaskRunStatus.ZOMBIE
    run.finished_at = _now()
    run.error_text = (run.error_text or "") + f"\n[zombie] {reason}"
    reg = db.get(SocTaskRegistry, run.task_key)
    if reg is not None and reg.current_run_id == run_id:
        reg.current_run_id = None
        reg.lock_owner = None
        reg.last_status = TaskRunStatus.ZOMBIE
        reg.consecutive_failures = (reg.consecutive_failures or 0) + 1
    db.commit()


def reconcile_on_startup(db: Session) -> dict:
    """启动时把残留 running run 标 unknown，清 registry 锁字段。

    必须在 lifespan 内 scheduler 启动之前调用（v0.4 P1-2）。
    """
    now = _now()
    running_runs = list_running_runs(db)
    count = 0
    for run in running_runs:
        run.status = TaskRunStatus.UNKNOWN
        run.finished_at = now
        run.error_text = "process restarted while running"
        count += 1
        reg = db.get(SocTaskRegistry, run.task_key)
        if reg is not None and reg.current_run_id == run.id:
            reg.current_run_id = None
            reg.lock_owner = None
            reg.last_status = TaskRunStatus.UNKNOWN
    db.commit()
    logger.info("startup reconcile: marked %d running runs as unknown", count)
    return {"marked_unknown": count}
