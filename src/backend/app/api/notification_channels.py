"""
通知通道管理 API（OH-NOT-F2 · Phase 1 · admin only）

CLAUDE.md §1.3 admin bypass + §0 配置中心 11 个调用点迁移。
Phase 1：admin 通道 CRUD + 配置 email SMTP；
Phase 2：test 端点实际发邮件（Phase 1 仅校验配置完整性）。
"""

from typing import List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status, Body
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.permissions import require_admin
from app.models import User
from app.schemas.notification_channel import (
    ChannelTestRequest,
    ChannelTestResult,
    NotificationChannelOut,
    NotificationChannelUpdate,
)
from app.services.notification_channel_service import (
    EMAIL_CHANNEL_CODE,
    NotificationChannelService,
)

router = APIRouter(prefix="/notification-channels", tags=["通知通道管理"])


def _redact_config(config: dict) -> dict:
    """出参时把 password 字段脱敏为 '***'"""
    if not isinstance(config, dict):
        return config
    redacted = dict(config)
    if "password" in redacted and redacted["password"]:
        redacted["password"] = "***"
    return redacted


@router.get("", response_model=List[NotificationChannelOut])
def list_channels(
    enabled_only: bool = Query(False, description="仅列出 enabled=true 的通道"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出所有通道。"""
    svc = NotificationChannelService(db)
    channels = svc.list_channels(enabled_only=enabled_only)
    return [
        NotificationChannelOut(
            id=ch.id,
            code=ch.code,
            name=ch.name,
            enabled=ch.enabled,
            config_json=_redact_config(ch.config_json or {}),
            created_at=ch.created_at,
            updated_at=ch.updated_at,
        )
        for ch in channels
    ]


@router.get("/{channel_id}", response_model=NotificationChannelOut)
def get_channel(
    channel_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = NotificationChannelService(db)
    ch = svc.get_by_id(channel_id)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")
    return NotificationChannelOut(
        id=ch.id,
        code=ch.code,
        name=ch.name,
        enabled=ch.enabled,
        config_json=_redact_config(ch.config_json or {}),
        created_at=ch.created_at,
        updated_at=ch.updated_at,
    )


@router.put("/{channel_id}", response_model=NotificationChannelOut)
def update_channel(
    channel_id: int,
    body: NotificationChannelUpdate,
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """admin 更新通道（Phase 1 重点：email SMTP 配置）。"""
    svc = NotificationChannelService(db)
    ch = svc.get_by_id(channel_id)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")

    # email 通道校验：config_json 完整 + 密码加密
    if ch.code == EMAIL_CHANNEL_CODE and body.config_json is not None:
        errors = svc.validate_email_config(body.config_json)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"validation_errors": errors},
            )

    updated = svc.update_channel(
        channel_id,
        name=body.name,
        enabled=body.enabled,
        config_json=body.config_json,
    )
    return NotificationChannelOut(
        id=updated.id,
        code=updated.code,
        name=updated.name,
        enabled=updated.enabled,
        config_json=_redact_config(updated.config_json or {}),
        created_at=updated.created_at,
        updated_at=updated.updated_at,
    )


@router.post("/{channel_id}/test", response_model=ChannelTestResult)
def test_channel(
    channel_id: int,
    body: ChannelTestRequest = ChannelTestRequest(),
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db),
    actual: bool = Query(
        False,
        description="Phase 2: true=真发邮件 (发到 to_address 或 admin 自己), false=仅 SMTP socket 测试 (Phase 1 行为)",
    ),
):
    """admin 手动测试通道。

    - actual=false (默认): 仅 SMTP socket 测试 (Phase 1 行为)
    - actual=true (Phase 2): 真发邮件给 to_address (或 admin 自己) 并返回发送结果
    """
    import time as _time

    svc = NotificationChannelService(db)
    ch = svc.get_by_id(channel_id)
    if ch is None:
        raise HTTPException(status_code=404, detail=f"Channel {channel_id} not found")

    if ch.code != EMAIL_CHANNEL_CODE:
        raise HTTPException(
            status_code=400,
            detail=f"Phase 1 仅 email 通道支持 test，{ch.code} 不支持",
        )

    if not ch.enabled:
        raise HTTPException(status_code=400, detail="Channel disabled")

    cfg = svc.get_email_config(use_cache=False)
    if cfg is None:
        raise HTTPException(status_code=400, detail="Email config missing")

    errors = svc.validate_email_config(cfg)
    if errors:
        return ChannelTestResult(
            success=False,
            message=f"配置不完整: {'; '.join(errors)}",
            smtp_host=cfg.get("host"),
            smtp_port=cfg.get("port"),
            elapsed_ms=0,
        )

    # Phase 1 行为: SMTP socket 连接测试 (不实际发邮件)
    if not actual:
        import socket

        host = cfg.get("host")
        port = int(cfg.get("port", 587))
        t0 = _time.time()
        try:
            sock = socket.create_connection((host, port), timeout=5)
            sock.close()
            elapsed_ms = int((_time.time() - t0) * 1000)
            return ChannelTestResult(
                success=True,
                message=f"SMTP socket connect OK (Phase 1: not sending email yet)",
                smtp_host=host,
                smtp_port=port,
                elapsed_ms=elapsed_ms,
            )
        except Exception as e:  # noqa: BLE001
            elapsed_ms = int((_time.time() - t0) * 1000)
            return ChannelTestResult(
                success=False,
                message=f"SMTP connect failed: {type(e).__name__}: {e}",
                smtp_host=host,
                smtp_port=port,
                elapsed_ms=elapsed_ms,
            )

    # Phase 2 行为: 真发邮件
    import time
    from app.services.email_sender import send_email, EmailSendError
    from app.services.email_template_registry import get_template_registry

    # 决定收件邮箱
    to_addr = (body.to_address if body.to_address else current_user.email) if hasattr(body, 'to_address') else current_user.email
    if not to_addr:
        return ChannelTestResult(
            success=False,
            message="no to_address and admin user has no email",
            smtp_host=cfg.get("host"),
            smtp_port=cfg.get("port"),
            elapsed_ms=0,
        )

    # 渲染 test 模板
    registry = get_template_registry()
    template = registry.get("test") or registry.get_default()
    ctx = {
        "user": {"id": current_user.id, "username": current_user.username, "email": current_user.email},
        "notification": {
            "id": "",
            "title": "SMTP 配置测试",
            "content": "这是一封来自 AI-miniSOC 通知中心 SMTP 配置测试邮件。",
            "link": "http://localhost:5173/system/notification-channels",
            "created_at": None,
        },
        "type": "test",
        "test_time": datetime.utcnow().isoformat() + "Z",
    }

    t0 = time.time()
    try:
        import asyncio
        result = asyncio.run(send_email(
            cfg,
            to_addr=to_addr,
            subject=template.render_subject(ctx),
            text_body=template.render_text(ctx),
            html_body=template.render_html(ctx),
        ))
        return ChannelTestResult(
            success=result["success"],
            message=f"email sent to {to_addr}: {result['message']}",
            smtp_host=result["smtp_host"],
            smtp_port=result["smtp_port"],
            elapsed_ms=result["elapsed_ms"],
        )
    except EmailSendError as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return ChannelTestResult(
            success=False,
            message=f"send failed: {e}",
            smtp_host=cfg.get("host"),
            smtp_port=cfg.get("port"),
            elapsed_ms=elapsed_ms,
        )


__all__ = ["router"]