"""MCP Tools 包。

每个模块导出一个 `register(mcp)` 函数把该模块的 tools 注册到 FastMCP 实例。
"""
from app.mcp.tools import (
    ai_tools,
    alert_tools,
    asset_extra_tools,
    asset_tools,
    auth_tools,
    dict_tools,
    incident_tools,
    loki_tools,
    system_tools,
)


def register_all(mcp) -> None:
    """把全部 MCP tools 注册到给定的 FastMCP 实例"""
    system_tools.register(mcp)    # 免鉴权，最先注册
    auth_tools.register(mcp)
    asset_tools.register(mcp)
    asset_extra_tools.register(mcp)  # 资产补充：端口 / 数据源 / 概览
    alert_tools.register(mcp)
    incident_tools.register(mcp)
    ai_tools.register(mcp)
    loki_tools.register(mcp)
    dict_tools.register(mcp)  # 字典查询


__all__ = ["register_all"]