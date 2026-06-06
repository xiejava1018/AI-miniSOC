"""
站内通知 API

- GET    /notifications              当前用户通知列表（分页 + is_read 筛选）
- GET    /notifications/unread-count
- POST   /notifications/{id}/read    标记单条已读
- POST   /notifications/mark-all-read
- POST   /notifications/test         管理员手动测试（admin only）
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user, require_admin
from app.models import User
from app.schemas.notification import (
    MarkAllReadOut,
    NotificationListResponse,
    NotificationOut,
    NotificationTestRequest,
    UnreadCountOut,
)
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _to_out(n) -> NotificationOut:
    return NotificationOut.model_validate(n)


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_read: bool | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = NotificationService(db)
    items, total = svc.list_for_user(
        user_id=current_user.id, page=page, page_size=page_size, is_read=is_read
    )
    return NotificationListResponse(
        total=total,
        items=[_to_out(n) for n in items],
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=UnreadCountOut)
async def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = NotificationService(db)
    return UnreadCountOut(count=svc.unread_count(current_user.id))


@router.post("/{notification_id}/read", response_model=NotificationOut)
async def mark_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = NotificationService(db)
    ok = svc.mark_read(user_id=current_user.id, notif_id=notification_id)
    if not ok:
        raise HTTPException(status_code=404, detail="通知不存在或无权访问")
    # 返回最新行
    from sqlalchemy import select

    from app.models import Notification

    notif = db.execute(
        select(Notification).where(Notification.id == notification_id)
    ).scalar_one_or_none()
    return _to_out(notif)


@router.post("/mark-all-read", response_model=MarkAllReadOut)
async def mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    svc = NotificationService(db)
    updated = svc.mark_all_read(current_user.id)
    return MarkAllReadOut(updated=updated)


@router.post("/test", response_model=NotificationOut)
async def test_notification(
    body: NotificationTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """管理员手动测试通知：会推给自己 + 在线则实时收到 WS 帧"""
    svc = NotificationService(db)
    n = await svc.create(
        user_id=current_user.id,
        type="test",
        title=body.title,
        content=body.content,
        link=body.link,
    )
    return _to_out(n)
