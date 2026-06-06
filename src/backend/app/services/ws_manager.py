"""
WebSocket 连接管理器（单进程内存版）

MVP 阶段仅维护一个 `user_id -> set[WebSocket]` 的进程内 Map。
生产多 worker 部署时需替换为 Redis Pub/Sub 或 PG LISTEN/NOTIFY（v1.1 升级项）。
"""

import asyncio
import json
import logging
from typing import Any, Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """管理进程内所有 WebSocket 连接"""

    def __init__(self) -> None:
        self._connections: Dict[int, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, user_id: int) -> None:
        """注册一条新连接。accept 由调用方决定（鉴权后再 accept）。"""
        async with self._lock:
            self._connections.setdefault(user_id, set()).add(websocket)
        logger.info("WS connected: user_id=%s total=%d", user_id, len(self._connections[user_id]))

    def disconnect(self, websocket: WebSocket, user_id: int) -> None:
        """从 map 中移除连接（无需加锁，set.remove 已原子）"""
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                self._connections.pop(user_id, None)
        logger.info("WS disconnected: user_id=%s", user_id)

    async def send_to_user(self, user_id: int, payload: Dict[str, Any]) -> int:
        """向指定用户的所有连接推送。返回成功发送的连接数。"""
        if user_id not in self._connections:
            return 0
        text = json.dumps(payload, ensure_ascii=False, default=str)
        sent = 0
        dead: list[WebSocket] = []
        for ws in list(self._connections[user_id]):
            try:
                await ws.send_text(text)
                sent += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("WS send failed: user_id=%s err=%s", user_id, e)
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, user_id)
        return sent

    def is_online(self, user_id: int) -> bool:
        return user_id in self._connections and bool(self._connections[user_id])


# 模块级单例
ws_manager = ConnectionManager()
