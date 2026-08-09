"""资产管理 MCP tools：只暴露查询类，避免 Agent 误删。"""
from __future__ import annotations

from app.mcp.tools.base import call_api


def register(mcp) -> None:
    @mcp.tool(
        name="list_assets",
        description=(
            "查询资产列表。支持按 IP / 名称 / 类型 / 资产类型 / 重要等级 / 状态 / 网络区域 / 数据源过滤。"
            "返回分页结果。"
        ),
    )
    def list_assets(
        skip: int = 0,
        limit: int = 50,
        asset_ip: str = "",
        name: str = "",
        asset_type: str = "",
        criticality: str = "",
        asset_status: str = "",
        network_zone: str = "",
        data_source: str = "",
    ) -> dict:
        params: dict = {"skip": skip, "limit": min(limit, 500)}
        for k, v in {
            "asset_ip": asset_ip,
            "name": name,
            "asset_type": asset_type,
            "criticality": criticality,
            "asset_status": asset_status,
            "network_zone": network_zone,
            "data_source": data_source,
        }.items():
            if v:
                params[k] = v
        return call_api("GET", "/assets", params=params)

    @mcp.tool(
        name="get_asset",
        description="根据资产 ID 获取资产详情。",
    )
    def get_asset(asset_id: int) -> dict:
        return call_api("GET", f"/assets/{asset_id}")

    @mcp.tool(
        name="get_asset_summary",
        description="获取资产总览统计（按类型 / 重要等级 / 状态聚合）。",
    )
    def get_asset_summary() -> dict:
        return call_api("GET", "/assets/summary")