"""
用户通知偏好 API（OH-NOT-F2 · Phase 1）

CLAUDE.md §0 X1 矩阵：默认所有用户都接收通知。
本端点让用户主动关闭特定 (type, channel) 投递。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models import User
from app.schemas.notification_channel import (
    UserPrefItem,
    UserPrefListOut,
    UserPrefUpdate,
)
from app.services.notification_channel_service import NotificationChannelService

router = APIRouter(prefix="/notification-preferences", tags=["通知偏好"])


@router.get("/my", response_model=UserPrefListOut)
def list_my_prefs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出我当前的所有偏好。空表示使用默认（全收）。"""
    svc = NotificationChannelService(db)
    prefs = svc.get_user_prefs(current_user.id)
    return UserPrefListOut(
        items=[
            UserPrefItem(
                type=p.type,
                channel_code=p.channel_code,
                enabled=p.enabled,
            )
            for p in prefs
        ]
    )


@router.put("/my/{type}/{channel_code}", response_model=UserPrefItem)
def upsert_my_pref(
    type: str,
    channel_code: str,
    body: UserPrefUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新我对某个 (type, channel) 的偏好。

    body.enabled=false → 之后该 (type, channel) 不再投递给我。
    """
    svc = NotificationChannelService(db)
    pref = svc.upsert_user_pref(
        user_id=current_user.id,
        type=type,
        channel_code=channel_code,
        enabled=body.enabled,
    )
    return UserPrefItem(
        type=pref.type,
        channel_code=pref.channel_code,
        enabled=pref.enabled,
    )


__all__ = ["router"]