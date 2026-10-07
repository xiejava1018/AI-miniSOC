"""
通知投递日志 API（OH-NOT-F2 Phase 3 · admin only）

observability：多通道投递状态/重试/错误可查询。
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func as sa_func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.permissions import require_admin
from app.models import User
from app.models.notification_channel import NotificationDispatchLog

router = APIRouter(prefix="/notification-dispatch-logs", tags=["通知投递日志"])


class DispatchLogItem(BaseModel):
    id: str
    notification_id: Optional[str] = None
    user_id: int
    channel_code: str
    status: str
    error_text: Optional[str] = None
    sent_at: Optional[str] = None
    retry_count: int
    next_retry_at: Optional[str] = None
    correlation_id: Optional[str] = None
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class DispatchLogPage(BaseModel):
    items: List[DispatchLogItem]
    total: int
    page: int
    page_size: int


@router.get("", response_model=DispatchLogPage)
def list_dispatch_logs(
    channel_code: Optional[str] = Query(None, description="inbox / email"),
    status: Optional[str] = Query(
        None, description="pending / sent / failed / bounced / skipped_pref"
    ),
    user_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """投递日志分页查询（admin）。按 created_at 倒序。"""
    stmt = select(NotificationDispatchLog)
    count_stmt = select(sa_func.count(NotificationDispatchLog.id))
    conds = []
    if channel_code:
        conds.append(NotificationDispatchLog.channel_code == channel_code)
    if status:
        conds.append(NotificationDispatchLog.status == status)
    if user_id is not None:
        conds.append(NotificationDispatchLog.user_id == user_id)
    for c in conds:
        stmt = stmt.where(c)
        count_stmt = count_stmt.where(c)

    total = db.execute(count_stmt).scalar() or 0
    rows = (
        db.execute(
            stmt.order_by(NotificationDispatchLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        .scalars()
        .all()
    )

    def _iso(v):
        return v.isoformat() if v else None

    return DispatchLogPage(
        items=[
            DispatchLogItem(
                id=str(r.id),
                notification_id=str(r.notification_id) if r.notification_id else None,
                user_id=r.user_id,
                channel_code=r.channel_code,
                status=r.status,
                error_text=r.error_text,
                sent_at=_iso(r.sent_at),
                retry_count=r.retry_count or 0,
                next_retry_at=_iso(r.next_retry_at),
                correlation_id=r.correlation_id,
                created_at=_iso(r.created_at),
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


__all__ = ["router"]
