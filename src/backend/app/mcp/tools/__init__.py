"""MCP Tools 包。

每个模块导出一个 `register(mcp)` 函数把该模块的 tools 注册到 FastMCP 实例。
"""
from app.mcp.tools import (
    ai_tools,
    alert_tools,
    asset_extra_tools,
    asset_audit,
    asset_fusion,
    asset_priority,
    asset_query_v2,
    asset_tools,
    auth_tools,
    dict_tools,
    incident_tools,
    loki_tools,
    behavior_profile_tools,
    system_tools,
    graph_tools,
)


def register_all(mcp) -> None:
    """把全部 MCP tools 注册到给定的 FastMCP 实例"""
    system_tools.register(mcp)    # 免鉴权，最先注册
    auth_tools.register(mcp)
    asset_tools.register(mcp)
    asset_extra_tools.register(mcp)  # 资产补充：端口 / 数据源 / 概览
    asset_query_v2.register(mcp)  # OH-5.2 资产问答·本体驱动版
    asset_fusion.register(mcp)  # OH-5.3 融合助手（列表/详情/裁决）
    asset_audit.register(mcp)  # OH-5.4 稽核助手（定级/覆盖率/数据健康/对账）
    asset_priority.register(mcp)  # OH-5.5 优先级助手（降级版）
    alert_tools.register(mcp)
    incident_tools.register(mcp)
    ai_tools.register(mcp)
    loki_tools.register(mcp)
    behavior_profile_tools.register(mcp)
    dict_tools.register(mcp)  # 字典查询
    graph_tools.register(mcp)  # 资产知识图谱关系类（v1）


__all__ = ["register_all"]