"""
MCP Key 认证中间件（传输层）。

包在 MCP 组合 Starlette app（/mcp streamable HTTP + /sse SSE）最外层：
- 无 Authorization 头：mcp.auth.required=false（默认）→ 放行（兼容 set_mcp_credentials
  旧流程）；true → 401
- Authorization: Bearer sk-mcp-xxx → 走 soc_mcp_keys 校验（Agent A 的
  app.services.mcp_key_service.validate_key_cached，含 TTL 缓存）：
  - 通过 → 以绑定用户身份免密签发 JWT（app.core.auth.create_access_token，自动带 jti）
    → TokenManager.inject_identity（优先级高于 set_mcp_credentials 会话凭证）
    → touch_last_used 后台线程 fire-and-forget
  - 失败 → 401 {"error": "key_invalid|key_revoked|key_expired|user_disabled"}；
    按客户端 IP 连续失败计数，超阈值锁定（429）

实现说明：
- **纯 ASGI 中间件**而非 BaseHTTPMiddleware：SSE 长连接流式响应零包装、零缓冲风险
- **同步 DB 调用一律 anyio.to_thread.run_sync**：MCP uvicorn 独立线程跑自己的事件循环，
  SQLAlchemy 是同步的，绝不能堵 loop
- app.services.mcp_key_service 用**函数内局部 import**：保持模块可独立导入
  （单测 monkeypatch 该模块属性即可生效）
"""
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import anyio

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 按 IP 失败计数 / 锁定（进程内；与 auth.py 的登录失败计数（按 username）独立）
# {ip: {"count": int, "first_fail_at": float, "locked_until": float}}
# ---------------------------------------------------------------------------
_FAILURES: dict[str, dict[str, float]] = {}
_FAIL_LOCK = threading.Lock()

# touch_last_used 的单线程后台池（fire-and-forget，避免每请求开新线程）
_TOUCH_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mcp-key-touch")


def reset_failures() -> None:
    """测试辅助：清空失败计数/锁定状态"""
    with _FAIL_LOCK:
        _FAILURES.clear()


def _client_ip(scope: dict) -> str:
    client = scope.get("client")
    if client and len(client) >= 1 and client[0]:
        return str(client[0])
    return "unknown"


def _is_locked(ip: str, now: float) -> bool:
    with _FAIL_LOCK:
        rec = _FAILURES.get(ip)
        if not rec or not rec.get("locked_until"):
            return False
        if now >= rec["locked_until"]:
            # 锁过期 → 清空，重新计数
            _FAILURES.pop(ip, None)
            return False
        return True


def _record_failure(ip: str, threshold: int, lock_minutes: float) -> bool:
    """记录一次校验失败；达到阈值则锁定。返回是否**刚触发**锁定。"""
    now = time.time()
    with _FAIL_LOCK:
        rec = _FAILURES.get(ip)
        if not rec or now - rec["first_fail_at"] > lock_minutes * 60:
            # 窗口外（或首次）→ 重新计数
            rec = {"count": 0, "first_fail_at": now, "locked_until": 0.0}
        rec["count"] += 1
        _FAILURES[ip] = rec
        if rec["count"] >= threshold and not rec["locked_until"]:
            rec["locked_until"] = now + lock_minutes * 60
            logger.warning(
                "MCP key auth: IP %s 连续失败 %d 次，锁定 %.0f 分钟",
                ip, rec["count"], lock_minutes,
            )
            return True
        return False


def _clear_failures(ip: str) -> None:
    with _FAIL_LOCK:
        _FAILURES.pop(ip, None)


def _json_response(
    send, status_code: int, payload: dict, extra_headers: list | None = None
) -> Any:
    """纯 ASGI 环境下发送 JSON 响应（返回 awaitable 组装由调用方 await）"""
    headers = [(b"content-type", b"application/json")]
    headers.extend(extra_headers or [])

    async def _send():
        await send({
            "type": "http.response.start",
            "status": status_code,
            "headers": headers,
        })
        await send({
            "type": "http.response.body",
            "body": json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        })

    return _send()


async def _read_config(key: str, default: Any) -> Any:
    """线程池里读配置中心（get_config 内部有 60s 缓存，冷路径才碰 DB）"""
    from app.services import mcp_key_service as key_svc

    return await anyio.to_thread.run_sync(key_svc.get_config, key, default)


class MCPKeyAuthMiddleware:
    """纯 ASGI 中间件：MCP 传输层的 Bearer sk-mcp-xxx Key 校验。"""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            # websocket / lifespan 等直接放行（本项目 MCP 只有 http transport）
            await self.app(scope, receive, send)
            return

        try:
            handled = await self._check(scope, receive, send)
        except Exception:  # noqa: BLE001
            logger.exception("MCP key auth middleware error")
            await _json_response(send, 500, {"error": "auth_internal_error"})
            return

        if handled is not None:
            await handled
            return

        await self.app(scope, receive, send)

    # ------------------------------------------------------------------ 校验
    async def _check(self, scope, receive, send):
        """
        返回 None → 放行下游；返回 awaitable → 直接以该响应终止。
        """
        from app.services import mcp_key_service as key_svc

        ip = _client_ip(scope)
        now = time.time()

        # 0) IP 锁定检查（最高优先级，锁定期间连有效 Key 也拒）
        if _is_locked(ip, now):
            with _FAIL_LOCK:
                rec = _FAILURES.get(ip) or {}
                retry_after = int(max(0.0, rec.get("locked_until", now) - now)) or 1
            return _json_response(
                send, 429, {"error": "locked"},
                extra_headers=[(b"retry-after", str(retry_after).encode())],
            )

        # 1) 解析 Authorization 头
        auth_header = ""
        for k, v in scope.get("headers", []):
            if k.decode("latin-1").lower() == "authorization":
                auth_header = v.decode("latin-1")
                break

        if not auth_header.strip():
            # 兼容模式：required=false 放行（现状）；true → 401
            required = bool(await _read_config("mcp.auth.required", False))
            if required:
                return _json_response(
                    send, 401, {"error": "key_invalid"},
                    extra_headers=[(b"www-authenticate", b"Bearer")],
                )
            return None  # 放行

        # 2) Bearer sk-mcp-* 解析
        parts = auth_header.split(None, 1)
        token = parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else ""
        if not token or not token.startswith("sk-mcp-"):
            threshold = int(await _read_config("mcp.key.failure_lock_threshold", 10))
            lock_minutes = float(await _read_config("mcp.key.failure_lock_minutes", 15))
            _record_failure(ip, threshold, lock_minutes)
            return _json_response(
                send, 401, {"error": "key_invalid"},
                extra_headers=[(b"www-authenticate", b"Bearer")],
            )

        # 3) Key 校验（同步 DB → 线程池）
        result = await anyio.to_thread.run_sync(key_svc.validate_key_cached, token)
        if not isinstance(result, dict) or not result.get("ok"):
            error = "key_invalid"
            if isinstance(result, dict):
                error = str(result.get("error") or "key_invalid")
            threshold = int(await _read_config("mcp.key.failure_lock_threshold", 10))
            lock_minutes = float(await _read_config("mcp.key.failure_lock_minutes", 15))
            newly_locked = _record_failure(ip, threshold, lock_minutes)
            if newly_locked:
                return _json_response(send, 429, {"error": "locked"})
            logger.info("MCP key auth rejected: ip=%s error=%s", ip, error)
            return _json_response(
                send, 401, {"error": error},
                extra_headers=[(b"www-authenticate", b"Bearer")],
            )

        # 4) 通过 → 免密签发 JWT + 注入身份 + touch_last_used 后台化
        user_id = result.get("user_id")
        username = str(result.get("username") or "")
        from app.core.auth import create_access_token
        from app.mcp.token_manager import get_token_manager

        jwt_token = create_access_token(
            data={
                "sub": str(user_id),
                "username": username,
                "role_code": result.get("role_code") or "",
                "via": "mcp_key",
            }
        )
        get_token_manager().inject_identity(user_id, username, jwt_token)

        key_id = result.get("key_id")
        if key_id is not None:
            _TOUCH_POOL.submit(_safe_touch, key_svc.touch_last_used, int(key_id))

        _clear_failures(ip)
        return None  # 放行


def _safe_touch(fn, key_id: int) -> None:
    """线程池里跑 touch_last_used，失败静默（契约：失败不阻塞请求）"""
    try:
        fn(key_id)
    except Exception:  # noqa: BLE001
        logger.debug("touch_last_used(%s) failed", key_id, exc_info=True)
