"""
WebSocket 端点

- /ws/notifications   站内通知实时推送

鉴权：从 query string `?token=<JWT>` 取 access token，复用 `core.auth.verify_token`。
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.auth import verify_token
from app.services.ws_manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/notifications")
async def ws_notifications(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="missing token")
        return

    # 鉴权：复用现有 verify_token（含 iss/aud/exp/jti 黑名单校验）
    try:
        payload = verify_token(token, "access")
    except Exception as e:  # noqa: BLE001
        logger.info("WS auth failed: %s", e)
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid token")
        return

    user_id = int(payload["sub"])

    await websocket.accept()
    await ws_manager.connect(websocket, user_id)

    # 推送一条 welcome 帧，标记连接建立成功
    try:
        await websocket.send_json({"type": "ready", "user_id": user_id})
    except Exception as e:  # noqa: BLE001
        logger.warning("WS welcome send failed: %s", e)
        ws_manager.disconnect(websocket, user_id)
        return

    try:
        # 阻塞主循环：仅消费客户端消息以保活（心跳），不依赖业务数据
        while True:
            msg = await websocket.receive_text()
            # 兼容 ping/pong 协议
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    except Exception as e:  # noqa: BLE001
        logger.warning("WS loop error user_id=%s: %s", user_id, e)
    finally:
        ws_manager.disconnect(websocket, user_id)


def _payload_to_ws(payload: Dict[str, Any]) -> Dict[str, Any]:
    """保持 ws_manager 推送结构稳定（占位，便于后续扩展）"""
    return payload
