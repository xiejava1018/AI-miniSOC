"""
Webhook 接收端点
用于接收来自 Wazuh 的实时通知

- POST /webhooks/wazuh                资产同步（已有）
- POST /webhooks/wazuh/alert          严重告警（level >= SEVERE_LEVEL(12)）→ 触发站内通知
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.core.alert_levels import SEVERE_LEVEL
from app.core.database import get_db
from app.schemas.sync import WebhookPayload, WebhookResponse
from app.services.asset_sync import AssetSyncService
from app.services.notification_service import NotificationService
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


async def verify_webhook_request(request: Request):
    """验证 Webhook 请求（IP白名单 + API Key）"""
    # IP 白名单验证
    client_ip = request.client.host
    if client_ip not in settings.webhook_allowed_ips_list:
        logger.warning(f"Webhook request from unauthorized IP: {client_ip}")
        raise HTTPException(
            status_code=403,
            detail=f"IP not allowed: {client_ip}"
        )

    # API Key 验证
    api_key = request.headers.get("X-API-Key")
    if not api_key or api_key != settings.WAZUH_WEBHOOK_KEY:
        logger.warning(f"Webhook request with invalid API key from {client_ip}")
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )

    return True


@router.post("/wazuh", response_model=WebhookResponse)
async def wazuh_webhook(
    payload: WebhookPayload,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_webhook_request)
):
    """接收 Wazuh Webhook 通知"""
    agent_id = payload.agent_id
    if not agent_id:
        raise HTTPException(status_code=400, detail="Missing agent_id")

    try:
        # 同步单个 agent
        sync_service = AssetSyncService(db)
        asset = sync_service.sync_single_agent_webhook(agent_id)

        logger.info(
            f"Webhook sync successful for agent {agent_id} "
            f"(asset_id: {asset.id})"
        )

        return WebhookResponse(
            success=True,
            message="Agent同步成功",
            asset_id=str(asset.id)
        )

    except Exception as e:
        logger.error(f"Webhook sync failed for agent {agent_id}: {e}")
        return WebhookResponse(
            success=False,
            message=str(e),
            asset_id=None
        )


class AlertWebhookPayload(BaseModel):
    """严重告警 webhook 负载

    来源：Wazuh / 第三方 SIEM 在 level >= SEVERE_LEVEL(12) 时主动推送
    """
    agent_id: Optional[str] = None
    rule_id: Optional[str] = None
    rule_level: int = 0
    rule_description: Optional[str] = None
    full_log: Optional[str] = None
    # 如需指定接收人；不传则广播给所有 admin
    target_user_id: Optional[int] = None


@router.post("/wazuh/alert", response_model=WebhookResponse)
async def wazuh_alert_webhook(
    payload: AlertWebhookPayload,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_webhook_request),
):
    """严重告警 webhook：level >= SEVERE_LEVEL(12) 时触发站内通知 + WS 推送

    目标用户：payload.target_user_id 指定；否则发给所有 is_admin=True 的用户。
    """
    if payload.rule_level < SEVERE_LEVEL:
        # 等级不够，直接忽略
        return WebhookResponse(success=True, message="alert level below threshold, ignored")

    # 解析目标用户
    from sqlalchemy import select
    from app.models.user import User, UserStatus

    if payload.target_user_id is not None:
        u = db.get(User, payload.target_user_id)
        targets = [u] if (u and u.status == UserStatus.ACTIVE) else []
    else:
        # 广播给所有 active 用户中 is_admin=True 的
        stmt = select(User).where(User.status == UserStatus.ACTIVE)
        targets = [u for u in db.execute(stmt).scalars().all() if u.is_admin]

    if not targets:
        logger.warning("alert webhook: no active admin to notify")
        return WebhookResponse(success=True, message="no active target users")

    title = f"严重告警 L{payload.rule_level}：{payload.rule_description or '未知规则'}"
    content = (payload.full_log or "")[:500]
    link = f"/alerts?rule_id={payload.rule_id}" if payload.rule_id else "/alerts"

    svc = NotificationService(db)
    delivered = 0
    for u in targets:
        try:
            await svc.create(
                user_id=u.id,
                type="alert",
                title=title,
                content=content,
                link=link,
            )
            delivered += 1
        except Exception as e:  # noqa: BLE001
            logger.warning("alert webhook notify user=%s failed: %s", u.id, e)

    return WebhookResponse(
        success=True,
        message=f"notified {delivered} user(s)",
    )
