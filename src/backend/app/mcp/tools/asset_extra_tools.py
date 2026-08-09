"""资产补充 MCP tools：端口 / 数据源 / 全局概览。

替代 fastapi-mcp 暴露的 B 部分同名工具（C 部分独立维护）。
"""
from __future__ import annotations

from app.mcp.tools.base import call_api


def register(mcp) -> None:
    @mcp.tool(
        name="list_asset_ports",
        description=(
            "获取指定资产的端口列表（资产的服务暴露面）。"
            "支持按 protocol (tcp/udp) 和 state (open/filtered/closed) 过滤。"
            "用于资产视角的攻击面分析（暴露端口、关联漏洞）。"
        ),
    )
    def list_asset_ports(
        asset_id: str,
        skip: int = 0,
        limit: int = 100,
        protocol: str = "",
        state: str = "",
    ) -> dict:
        """
        Args:
            asset_id: 资产 UUID
            skip: 分页偏移
            limit: 最大 500
            protocol: tcp / udp（可选）
            state: open / filtered / closed（可选）
        """
        params: dict = {"skip": skip, "limit": min(limit, 500)}
        if protocol:
            params["protocol"] = protocol
        if state:
            params["state"] = state
        return call_api("GET", f"/assets/{asset_id}/ports/", params=params)

    @mcp.tool(
        name="get_asset_overview",
        description=(
            "获取全 SOC 资产总览 KPI（无需参数）。"
            "返回：total_assets / high_risk_assets / alerts_24h / open_incidents，"
            "以及按类型/区域/重要等级的分布统计。Agent 启动时可一次拿到全局视图。"
        ),
    )
    def get_asset_overview() -> dict:
        return call_api("GET", "/assets/overview/")

    @mcp.tool(
        name="get_asset_sources",
        description=(
            "获取资产的所有数据来源（如 Wazuh / TP-Link 采集器 / 手动录入）。"
            "用于溯源：某条资产数据是从哪个采集器/手工录入来的。"
        ),
    )
    def get_asset_sources(asset_id: str) -> dict:
        """
        Args:
            asset_id: 资产 UUID
        """
        return call_api("GET", f"/assets/{asset_id}/sources/")