"""
Webhook 接收端点
用于接收来自 Wazuh 的实时通知
"""

from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas.sync import WebhookPayload, WebhookResponse
from app.services.asset_sync import AssetSyncService
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
