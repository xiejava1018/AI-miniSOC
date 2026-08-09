"""认证相关 MCP tools：登录 / 刷新 / 当前用户信息。"""
from __future__ import annotations

from app.mcp.tools.base import call_api


def register(mcp) -> None:
    @mcp.tool(
        name="login",
        description="用用户名密码登录 SOC，返回 access_token + refresh_token。推荐用 set_mcp_credentials 替代。",
    )
    def login(username: str, password: str) -> dict:
        """直接登录拿 token（不走 TokenManager，调用方自己保管）"""
        import httpx
        from app.core.config import settings
        with httpx.Client(timeout=10) as c:
            r = c.post(
                f"http://localhost:{settings.BACKEND_PORT}/api/v1/auth/login",
                json={"username": username, "password": password},
            )
            r.raise_for_status()
            data = r.json().get("data", r.json())
            return {
                "access_token": data["access_token"],
                "refresh_token": data["refresh_token"],
                "expires_in": data["expires_in"],
                "user": data.get("user"),
            }

    @mcp.tool(
        name="get_current_user",
        description="获取当前登录用户信息（验证 token 是否仍有效）。",
    )
    def get_current_user() -> dict:
        return call_api("GET", "/auth/me")

    @mcp.tool(
        name="logout",
        description="登出（撤销当前 token）。",
    )
    def logout() -> dict:
        return call_api("POST", "/auth/logout")