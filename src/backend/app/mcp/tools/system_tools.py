"""
免鉴权 MCP Tools：系统自我介绍 / 配置 MCP 凭证。

`get_system_info` 不需要 JWT，方便 Agent 启动时先调用。
`set_mcp_credentials` 由运维触发，把账号密码交给 TokenManager。
"""
from __future__ import annotations

from app.mcp.tools.base import call_api
from app.mcp.token_manager import get_token_manager


def register(mcp) -> None:
    @mcp.tool(
        name="get_system_info",
        description=(
            "获取 SOC 系统元信息（应用名 / Logo / 版权 / 描述）。"
            "**免鉴权**，Agent 启动时可先调用本工具向用户自我介绍，"
            "再询问账号密码调用 set_mcp_credentials。"
        ),
    )
    def get_system_info() -> dict:
        return call_api("GET", "/public/system-info", with_auth=False)

    @mcp.tool(
        name="get_token_status",
        description=(
            "查询当前 MCP Token 状态（是否配置、是否有效、过期时间）。"
            "诊断 token 是否过期时调用。"
        ),
    )
    def get_token_status() -> dict:
        return get_token_manager().status()

    @mcp.tool(
        name="set_mcp_credentials",
        description=(
            "配置 MCP Agent 的账号密码。TokenManager 会自动登录并后台刷新 JWT。"
            "**只需调用一次**，后续所有工具自动复用；token 过期前 5 分钟自动续期。"
            "若 token 彻底失效（账号被锁 / 密码改 / refresh 过期），"
            "需重新调用本工具。"
        ),
    )
    def set_mcp_credentials(username: str, password: str) -> dict:
        """
        Args:
            username: SOC 登录用户名
            password: SOC 登录密码
        """
        bundle = get_token_manager().configure(username=username, password=password)
        return {
            "success": True,
            "username": bundle.username,
            "access_expires_in_seconds": int(bundle.expires_at - bundle.expires_at + bundle.access_token.__len__() * 0),  # noqa
            "message": "凭证已配置，token 后台自动刷新已启动",
        }