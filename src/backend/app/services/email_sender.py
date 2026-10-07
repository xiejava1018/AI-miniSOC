"""
邮件发送服务（OH-NOT-F2 · Phase 2）

CLAUDE.md §0 异步 SMTP + §4.7 错误可观测。

设计：
- 用 aiosmtplib 异步 SMTP（FastAPI 生态友好）
- 接 soc_notification_channels.email.config_json（CLAUDE.md §4.6 11 个调用点迁移）
- Phase 2 仅 send() 给一个 Notification 渲染模板 + 投递
- 失败抛 EmailSendError，调用方（worker）决定 retry
- TLS/STARTTLS/Plain 三种模式（端口自动匹配）
"""

from __future__ import annotations

import asyncio
import logging
from email.message import EmailMessage
from typing import Any, Dict, List, Optional

import aiosmtplib

from app.models import User
from app.models.notification import Notification

logger = logging.getLogger(__name__)


class EmailSendError(Exception):
    """邮件发送失败（4xx 不重试 / 5xx + 网络重试）。"""


async def send_email(
    cfg: Dict[str, Any],
    *,
    to_addr: str,
    subject: str,
    text_body: str,
    html_body: Optional[str] = None,
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    is_test: bool = False,
) -> Dict[str, Any]:
    """通过 aiosmtplib 异步发邮件。

    Args:
        cfg: 来自 soc_notification_channels.email.config_json 的 SMTP 配置
              (host / port / user / password / use_tls / from_addr / from_name)
        to_addr: 收件邮箱
        subject: 主题
        text_body: 纯文本正文 (CLAUDE.md §0 邮件可读性)
        html_body: HTML 正文 (可选)
        cc/bcc: 抄送
        is_test: Phase 1 test 端点用 True → 仅 SMTP socket 测试，不真发

    Returns:
        dict: {success, message, smtp_host, smtp_port, elapsed_ms}

    Raises:
        EmailSendError: 网络/认证/SMTP 错误
    """
    host = cfg.get("host")
    user = cfg.get("user")
    password = cfg.get("password")
    from_addr = cfg.get("from_addr", user)
    from_name = cfg.get("from_name", "AI-miniSOC 通知")
    use_tls = cfg.get("use_tls", True)
    port = int(cfg.get("port", 587))

    if not (host and user and password and from_addr):
        raise EmailSendError("incomplete SMTP config: host/user/password/from_addr required")

    # 构造 MIMEMultipart 邮件
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_addr}>"
    msg["To"] = to_addr
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg.set_content(text_body or "")
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    import time
    t0 = time.time()
    try:
        if is_tls_port_465(use_tls, port):
            # SMTPS (隐式 TLS, 端口 465)
            await aiosmtplib.send(
                msg,
                hostname=host,
                port=port,
                username=user,
                password=password,
                use_tls=True,  # implicit TLS
            )
        else:
            # STARTTLS (端口 587) 或 plain (端口 25) — aiosmtplib 默认行为
            await aiosmtplib.send(
                msg,
                hostname=host,
                port=port,
                username=user,
                password=password,
                use_tls=use_tls,
            )
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.info("email sent: to=%s subject=%r elapsed=%dms", to_addr, subject[:50], elapsed_ms)
        return {
            "success": True,
            "message": "sent OK",
            "smtp_host": host,
            "smtp_port": port,
            "elapsed_ms": elapsed_ms,
        }
    except aiosmtplib.SMTPAuthenticationError as e:
        # 4xx auth: 不重试
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.warning("email auth failed (no retry): %s", e)
        raise EmailSendError(f"auth failed: {e}") from e
    except (aiosmtplib.SMTPConnectTimeoutError, aiosmtplib.SMTPTimeoutError, OSError, asyncio.TimeoutError) as e:
        # 网络/超时：可重试
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.warning("email network error (retryable): %s", e)
        raise EmailSendError(f"network/timeout: {e}") from e
    except aiosmtplib.SMTPException as e:
        # 其他 SMTP 错误: 5xx 一般 retry / 4xx 不 retry — 默认 retry
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.warning("email SMTP error: %s", e)
        raise EmailSendError(f"SMTP: {e}") from e


def is_tls_port_465(use_tls: bool, port: int) -> bool:
    """判断端口 465 → implicit TLS; 其他端口 STARTTLS/plain (CLAUDE.md §0 SMTP 标准)。"""
    return use_tls and port == 465


# ============================================================
# 模板渲染（Phase 2 入口）
# ============================================================

async def render_and_send(
    cfg: Dict[str, Any],
    *,
    user: User,
    notification: Notification,
    type: str,
    extra_context: Optional[Dict[str, Any]] = None,
    db=None,
) -> Dict[str, Any]:
    """根据 notification.type 选模板 + 渲染 + 投递。

    Phase 3：DB 覆盖模板优先（传 db 时自动 ensure）；邮件 footer 注入
    退订链接（unsubscribe_url，HMAC 签名，点击即关该类型邮件投递）。
    """
    from app.services.email_template_registry import get_template_registry
    from app.services.unsubscribe_token import build_unsubscribe_url

    registry = get_template_registry()
    if db is not None:
        try:
            registry.ensure_db_overrides(db)
        except Exception:  # noqa: BLE001
            logger.warning("db template override load failed; builtin used")
    template = registry.get(type)
    if template is None:
        # fallback 到通用模板
        template = registry.get_default()

    app_base_url = str(cfg.get("app_base_url", "http://localhost:8000"))
    unsubscribe_url = build_unsubscribe_url(app_base_url, user.id, type)

    ctx: Dict[str, Any] = {
        "user": {"id": user.id, "username": user.username, "email": user.email},
        "notification": {
            "id": str(notification.id),
            "title": notification.title,
            "content": notification.content,
            "link": notification.link,
            "created_at": notification.created_at.isoformat() if notification.created_at else None,
        },
        "type": type,
        "unsubscribe_url": unsubscribe_url,
    }
    if extra_context:
        ctx.update(extra_context)

    subject = template.render_subject(ctx)
    text_body = template.render_text(ctx)
    html_body = template.render_html(ctx)

    return await send_email(
        cfg,
        to_addr=user.email,
        subject=subject,
        text_body=text_body,
        html_body=html_body,
    )