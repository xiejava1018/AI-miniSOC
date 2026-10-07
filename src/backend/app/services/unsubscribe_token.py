"""
邮件退订令牌（OH-NOT-F2 Phase 3）

设计：无状态 HMAC-SHA256 签名（复用 settings.SECRET_KEY，不建表）。
- payload: user_id:type:exp_unix（type 可为 "*" 表示全类型）
- 签名: base64url(HMAC(SECRET_KEY, payload))
- 有效期默认 30 天；点击后端点把 (user, type, 'email') 偏好置 disabled

CLAUDE.md §0「用户可观测的退订能力」+ §4.13（token 校验失败返回明确错误）。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Optional

from app.core.config import settings

TOKEN_TTL_S = 30 * 24 * 3600  # 30 天


def _sign(payload: str) -> str:
    key = (settings.SECRET_KEY or "").encode()
    mac = hmac.new(key, payload.encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).rstrip(b"=").decode()


def make_unsubscribe_token(user_id: int, notif_type: str = "*",
                           ttl_s: int = TOKEN_TTL_S) -> str:
    """生成退订 token。"""
    exp = int(time.time()) + ttl_s
    payload = f"{user_id}:{notif_type}:{exp}"
    encoded = base64.urlsafe_b64encode(payload.encode()).rstrip(b"=").decode()
    return f"{encoded}.{_sign(payload)}"


def verify_unsubscribe_token(token: str) -> Optional[tuple[int, str]]:
    """校验 token。返回 (user_id, type) 或 None（无效/过期/签名不符）。"""
    try:
        encoded, sig = token.split(".", 1)
        # 补齐 base64 padding
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = base64.urlsafe_b64decode(padded.encode()).decode()
        if not hmac.compare_digest(_sign(payload), sig):
            return None
        user_id_s, notif_type, exp_s = payload.split(":", 2)
        if int(exp_s) < int(time.time()):
            return None
        return int(user_id_s), notif_type
    except Exception:  # noqa: BLE001
        return None


def build_unsubscribe_url(app_base_url: str, user_id: int, notif_type: str) -> str:
    token = make_unsubscribe_token(user_id, notif_type)
    return f"{app_base_url.rstrip('/')}/api/v1/notification-preferences/unsubscribe?token={token}"
