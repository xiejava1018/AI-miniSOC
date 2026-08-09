"""
MCP Tools 基类与共享 HTTP 客户端。

所有 MCP tool 通过 `call_api()` 调后端，自动注入 Authorization 头。
Token 由 TokenManager 管理，自动刷新。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.core.config import settings
from app.mcp.token_manager import TokenExpiredError, get_token_manager

logger = logging.getLogger(__name__)

# 默认 API 基址（http://host:8000/api/v1）
DEFAULT_API_BASE = f"http://localhost:{settings.BACKEND_PORT}/api/v1"


class APIError(RuntimeError):
    """调后端 API 失败（非 2xx）"""
    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"HTTP {status_code}: {body}")


def call_api(
    method: str,
    path: str,
    *,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    with_auth: bool = True,
    api_base: Optional[str] = None,
    timeout: float = 30.0,
) -> dict:
    """
    调后端 FastAPI，自动处理鉴权 + 响应包装。

    Args:
        method: GET / POST / PUT / DELETE
        path: 例如 "/assets?page=1"，不带 /api/v1 前缀
        params: query string
        json_body: request body
        with_auth: False 时不注入 Authorization（公开接口如 /public/system-info）
        api_base: 自定义 API 基址

    Returns:
        解开 {code,msg,data} 包装后的 data 字段（通常就是 dict/list）

    Raises:
        TokenExpiredError: token 已彻底失效
        APIError: 后端返回非 2xx
    """
    base = api_base or DEFAULT_API_BASE
    headers: dict[str, str] = {"Content-Type": "application/json"}

    if with_auth:
        try:
            token = get_token_manager().get_token()
            headers["Authorization"] = f"Bearer {token}"
        except TokenExpiredError as e:
            # 转成友好错误返回给 Agent
            raise TokenExpiredError(
                f"MCP 凭证失效：{e}。请通过 set_mcp_credentials 工具重新配置账号密码。"
            ) from e

    url = f"{base}{path}"
    logger.debug("MCP → %s %s", method, url)

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        r = client.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=headers,
        )

    if r.status_code >= 400:
        logger.warning("MCP API error: %s %s → %s %s", method, url, r.status_code, r.text[:300])
        raise APIError(r.status_code, _safe_json(r))

    body = _safe_json(r)
    # 解开响应包装中间件（HTTP 200 + body.code=业务码）
    if isinstance(body, dict) and "code" in body and "data" in body:
        if body.get("code") not in (200, 0):
            raise APIError(body.get("code", -1), body)
        return body.get("data", body)
    return body


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return {"raw_text": r.text}


def auth_headers() -> dict[str, str]:
    """返回当前 Authorization header（供需要自定义请求的场景）"""
    return {"Authorization": f"Bearer {get_token_manager().get_token()}"}