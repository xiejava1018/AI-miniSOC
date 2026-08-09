"""字典 MCP tools：用于解析告警类型/严重等级/事件分类等枚举值。

替代 fastapi-mcp 暴露的 B 部分同名工具（C 部分独立维护）。
"""
from __future__ import annotations

from app.mcp.tools.base import call_api


def register(mcp) -> None:
    @mcp.tool(
        name="list_dicts",
        description=(
            "查询字典列表（分页）。可用于探索 SOC 系统中定义的所有字典类型。"
            "支持按 dict_type 过滤、按 search 模糊匹配。"
        ),
    )
    def list_dicts(
        page: int = 1,
        page_size: int = 20,
        search: str = "",
        dict_type: str = "",
    ) -> dict:
        """
        Args:
            page: 页码（从1开始）
            page_size: 每页大小（最大 100）
            search: 搜索关键词（可选）
            dict_type: 按字典类型过滤（可选）
        """
        params: dict = {"page": page, "page_size": min(page_size, 100)}
        if search:
            params["search"] = search
        if dict_type:
            params["dict_type"] = dict_type
        return call_api("GET", "/dicts", params=params)

    @mcp.tool(
        name="list_dict_types",
        description=(
            "列出所有字典分类（如 alert_level / event_severity / asset_type 等）。"
            "Agent 在解析告警或事件时可先调此工具，了解系统支持的枚举值。"
        ),
    )
    def list_dict_types() -> list[str]:
        return call_api("GET", "/dicts/types")

    @mcp.tool(
        name="get_dicts_by_type",
        description=(
            "按字典类型获取全部字典项（不分页，前端缓存用）。"
            "例：get_dicts_by_type('alert_level') 返回所有告警等级定义。"
        ),
    )
    def get_dicts_by_type(dict_type: str) -> list[dict]:
        """
        Args:
            dict_type: 字典类型（如 'alert_level'、'event_severity'）
        """
        return call_api("GET", f"/dicts/{dict_type}/items")