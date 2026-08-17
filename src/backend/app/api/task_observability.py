"""
后台任务可观测性 API（v0.4.2 Phase 1.3）。

端点：
- GET    /tasks                    列出 registry（分页）
- GET    /tasks/{task_key}         单个 registry 详情
- GET    /tasks/{task_key}/runs    该任务的 run 历史（分页）
- GET    /tasks/runs/{run_id}      单个 run 详情
- POST   /tasks/{task_key}/trigger 手动触发（202 fire-and-forget）
- POST   /tasks/{task_key}/cancel/{run_id} 取消 in-flight run
- PATCH  /tasks/{task_key}         toggle enabled / 更新 timeout_s
- GET    /tasks/summary            看板汇总
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.task_observability import (
    SocTaskRegistry,
    SocTaskRun,
    TaskRunStatus,
)
from app.models.user import User
from app.services.audit_log_service import AuditLogService
from app.services.task_observability.decorator import track_task
from app.services.task_observability.notification_queue import (
    notification_queue,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["后台任务"])


# ---------------------------------------------------------------------------
# Schemas

class RegistryOut(BaseModel):
    task_key: str
    task_name: str
    task_type: str
    owner_module: Optional[str] = None
    schedule_expr: Optional[str] = None
    expected_interval_s: Optional[int] = None
    timeout_s: int
    enabled: bool
    current_run_id: Optional[str] = None
    lock_owner: Optional[str] = None
    last_run_at: Optional[datetime] = None
    last_status: Optional[str] = None
    last_error: Optional[str] = None
    last_duration_ms: Optional[int] = None
    last_stats: Optional[dict] = None
    consecutive_failures: int
    total_runs: int
    # Phase 2.4：当前运行进度（由 list/get 端点填充）
    current_run: Optional["RunOut"] = None

    class Config:
        from_attributes = True


class RunOut(BaseModel):
    id: str
    task_key: str
    trigger: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    status: str
    duration_ms: Optional[int] = None
    error_text: Optional[str] = None
    stats_json: Optional[dict] = None
    total: Optional[int] = None
    processed: Optional[int] = None
    percent: Optional[int] = None
    last_progress_at: Optional[datetime] = None
    correlation_id: Optional[str] = None
    host: Optional[str] = None
    triggered_by_user: Optional[str] = None

    @field_validator("id", mode="before")
    @classmethod
    def _id_to_str(cls, v: Any) -> Any:
        """UUID → str（Pydantic v2 + from_attributes 不会自动转换）"""
        if v is not None and not isinstance(v, str):
            return str(v)
        return v

    class Config:
        from_attributes = True


# Phase 2.4：RegistryOut 有前向引用 RunOut，需要在 RunOut 定义后 rebuild
RegistryOut.model_rebuild()


class TriggerRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)
    correlation_id: Optional[str] = None


class TriggerResponse(BaseModel):
    run_id: str
    status: str = "pending"


class CancelResponse(BaseModel):
    cancelled: bool
    run_id: str


class ToggleRequest(BaseModel):
    enabled: Optional[bool] = None
    timeout_s: Optional[int] = Field(default=None, ge=30, le=86400)
    reason: str = Field(..., min_length=3, max_length=500)


class SummaryOut(BaseModel):
    total_tasks: int
    enabled_tasks: int
    disabled_tasks: int
    running_runs: int
    zombie_runs: int
    consecutive_failed_tasks: int
    queue_size: int


# ---------------------------------------------------------------------------
# Registry 视图

def _fill_current_run(db: Session, out: dict) -> dict:
    """Phase 2.4：把 current_run 进度信息填进 RegistryOut dict。"""
    run_id = out.get("current_run_id")
    if not run_id:
        out["current_run"] = None
        return out
    run = db.get(SocTaskRun, uuid.UUID(run_id))
    if run is None or run.status != TaskRunStatus.RUNNING:
        out["current_run"] = None
        return out
    out["current_run"] = RunOut.model_validate(run).model_dump(mode="json")
    return out


@router.get("", response_model=dict)
def list_registries(
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    q = select(SocTaskRegistry).order_by(SocTaskRegistry.task_key)
    total = db.query(SocTaskRegistry).count()
    rows = db.execute(q.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    records = []
    for r in rows:
        d = RegistryOut.model_validate(r).model_dump(mode="json")
        records.append(_fill_current_run(db, d))
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": records,
    }


@router.get("/summary", response_model=SummaryOut)
def tasks_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    total = db.query(SocTaskRegistry).count()
    enabled = db.query(SocTaskRegistry).filter(SocTaskRegistry.enabled.is_(True)).count()
    running = db.query(SocTaskRun).filter(SocTaskRun.status == TaskRunStatus.RUNNING).count()
    zombie = db.query(SocTaskRun).filter(SocTaskRun.status == TaskRunStatus.ZOMBIE).count()
    consecutive = (
        db.query(SocTaskRegistry)
        .filter(SocTaskRegistry.consecutive_failures > 0)
        .count()
    )
    return SummaryOut(
        total_tasks=total,
        enabled_tasks=enabled,
        disabled_tasks=total - enabled,
        running_runs=running,
        zombie_runs=zombie,
        consecutive_failed_tasks=consecutive,
        queue_size=notification_queue.size(),
    )


@router.get("/{task_key}", response_model=RegistryOut)
def get_registry(
    task_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reg = db.get(SocTaskRegistry, task_key)
    if reg is None:
        raise HTTPException(status_code=404, detail=f"task '{task_key}' not found")
    out = RegistryOut.model_validate(reg).model_dump(mode="json")
    return _fill_current_run(db, out)


# ---------------------------------------------------------------------------
# Run 视图

@router.get("/{task_key}/runs", response_model=dict)
def list_runs(
    task_key: str,
    page: int = 1,
    page_size: int = 20,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    page = max(1, page)
    page_size = min(max(1, page_size), 200)
    q = select(SocTaskRun).where(SocTaskRun.task_key == task_key)
    if status_filter:
        q = q.where(SocTaskRun.status == status_filter)
    q = q.order_by(desc(SocTaskRun.started_at))
    total = (
        db.query(SocTaskRun)
        .filter(SocTaskRun.task_key == task_key)
        .filter(SocTaskRun.status == status_filter if status_filter else True)
        .count()
    )
    rows = db.execute(q.offset((page - 1) * page_size).limit(page_size)).scalars().all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "records": [RunOut.model_validate(r).model_dump(mode="json") for r in rows],
    }


@router.get("/runs/{run_id}", response_model=RunOut)
def get_run(
    run_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = db.get(SocTaskRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run '{run_id}' not found")
    return RunOut.model_validate(run)


# ---------------------------------------------------------------------------
# 操作：trigger / cancel / toggle

# 全局 in-flight trigger tasks（app.state 也会引用，这里是为了 cancel 能找到）
_inflight: dict[str, asyncio.Task] = {}


@router.post(
    "/{task_key}/trigger",
    response_model=TriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_task(
    task_key: str,
    payload: TriggerRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """手动触发任务。fire-and-forget，立即返回 run_id。"""
    reg = db.get(SocTaskRegistry, task_key)
    if reg is None:
        raise HTTPException(status_code=404, detail=f"task '{task_key}' not found")
    if not reg.enabled:
        raise HTTPException(status_code=400, detail="task is disabled; enable it first")

    # 找被 @track_task 包装的可调用对象（在 _TASK_HANDLERS 注册中心查）
    from app.services.task_observability.handlers import get_handler
    handler = get_handler(task_key)
    if handler is None:
        raise HTTPException(
            status_code=400,
            detail=f"no async handler registered for '{task_key}' "
                   "(scheduler may not have started yet, or task is thread-only)",
        )

    # 审计
    AuditLogService(db).create_audit_log(
        user_id=current_user.id,
        username=current_user.username,
        action="task.trigger",
        resource_type="task",
        resource_name=task_key,
        new_values={"reason": payload.reason, "correlation_id": payload.correlation_id},
    )
    db.commit()

    # 启异步 task
    async def _run():
        try:
            await handler(trigger="manual")
        except Exception:
            logger.exception("manual trigger for %s failed", task_key)

    task = asyncio.create_task(_run())
    run_id = str(uuid.uuid4())
    _inflight[run_id] = task
    task.add_done_callback(lambda t: _inflight.pop(run_id, None))

    return TriggerResponse(run_id=run_id, status="pending")


@router.post("/{task_key}/cancel/{run_id}", response_model=CancelResponse)
async def cancel_task(
    task_key: str,
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    task = _inflight.get(run_id)
    if task is None or task.done():
        raise HTTPException(status_code=404, detail="run not in flight or already finished")
    task.cancel()
    AuditLogService(db).create_audit_log(
        user_id=current_user.id,
        username=current_user.username,
        action="task.cancel",
        resource_type="task",
        resource_name=task_key,
        new_values={"run_id": run_id},
    )
    db.commit()
    return CancelResponse(cancelled=True, run_id=run_id)


@router.patch("/{task_key}", response_model=RegistryOut)
def toggle_task(
    task_key: str,
    payload: ToggleRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reg = db.get(SocTaskRegistry, task_key)
    if reg is None:
        raise HTTPException(status_code=404, detail=f"task '{task_key}' not found")

    changes = {"reason": payload.reason}
    if payload.enabled is not None:
        reg.enabled = payload.enabled
        changes["enabled"] = payload.enabled
    if payload.timeout_s is not None:
        reg.timeout_s = payload.timeout_s
        changes["timeout_s"] = payload.timeout_s

    AuditLogService(db).create_audit_log(
        user_id=current_user.id,
        username=current_user.username,
        action="task.toggle",
        resource_type="task",
        resource_name=task_key,
        new_values=changes,
    )
    db.commit()
    db.refresh(reg)
    return RegistryOut.model_validate(reg)
