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

# ============================================================
# Phase 3: 邮件退订（公开端点 — HMAC token 鉴权，不走 JWT）
# ============================================================

unsubscribe_router = APIRouter(prefix="/notification-preferences", tags=["通知偏好"])


@unsubscribe_router.get("/unsubscribe")
def unsubscribe(
    token: str,
    db: Session = Depends(get_db),
):
    """邮件一键退订：验证 HMAC token → 关闭 (user, type, email) 偏好。"""
    from fastapi.responses import HTMLResponse
    from app.services.unsubscribe_token import verify_unsubscribe_token

    result = verify_unsubscribe_token(token)
    if result is None:
        return HTMLResponse(
            "<h3>退订链接无效或已过期</h3>"
            "<p>请到 AI-miniSOC「系统管理 → 通知偏好」手动管理订阅。</p>",
            status_code=400,
        )
    user_id, notif_type = result
    svc = NotificationChannelService(db)
    if notif_type == "*":
        from app.services.email_template_registry import get_template_registry
        for t in get_template_registry().list_builtin_types():
            if t == "_default":
                continue
            svc.upsert_user_pref(user_id, t, "email", enabled=False)
        label = "所有类型"
    else:
        svc.upsert_user_pref(user_id, notif_type, "email", enabled=False)
        label = f"「{notif_type}」"

    return HTMLResponse(
        "<div style='font-family:Arial,sans-serif;padding:40px;text-align:center'>"
        f"<h2 style='color:#10b981'>已退订</h2>"
        f"<p>你将不再收到 {label} 的邮件通知。</p>"
        "<p style='color:#999'>站内信不受影响；可随时到 "
        "「系统管理 → 通知偏好」重新开启。</p>"
        "</div>"
    )
