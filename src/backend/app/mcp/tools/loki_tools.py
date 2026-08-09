"""
Loki 直连 MCP tools：Agent 可以直接探索原始日志，不走后端。

为什么单独搞一组直连 Loki 的 tools？
- 后端 /api/v1/browsing 之类的聚合查询是「已解释」的告警视图
- Agent 有时需要看原始日志（域名、IP、时间窗口）做归因分析
- 直连 Loki 让 Agent 可以灵活构造 LogQL，按需拉数据
"""
from __future__ import annotations

import logging
import time
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


def register(mcp) -> None:
    @mcp.tool(
        name="loki_query_range",
        description=(
            "查询 Loki 日志（时间范围 + LogQL）。"
            "返回 Loki 原生格式：{streams: [{labels, entries: [ts, line]}, ...]}。"
            "**注意**：纳秒时间戳、Loki 默认仅保留 7 天、最大 10000 条/次。"
        ),
    )
    def loki_query_range(
        query: str,
        hours: int = 24,
        limit: int = 1000,
        direction: str = "backward",
    ) -> dict:
        """
        Args:
            query: LogQL 查询字符串，如 {ip="192.168.0.2"} 或 {job="wazuh-alerts"} |= "error"
            hours: 时间窗口（最近 N 小时）
            limit: 最大返回条数（≤10000）
            direction: backward / forward
        """
        end = int(time.time() * 1e9)
        start = end - hours * 3600 * 1e9
        try:
            with httpx.Client(timeout=30) as c:
                r = c.get(
                    f"{settings.LOKI_API_URL}/loki/api/v1/query_range",
                    params={
                        "query": query,
                        "start": start,
                        "end": end,
                        "limit": min(limit, 10000),
                        "direction": direction,
                    },
                )
                r.raise_for_status()
                return r.json()
        except Exception as e:
            logger.warning("loki_query_range failed: %s", e)
            return {"error": str(e), "streams": []}

    @mcp.tool(
        name="loki_list_labels",
        description="列出 Loki 所有 label 名。Agent 可用来发现可过滤维度（如 ip / job / host）。",
    )
    def loki_list_labels() -> list[str]:
        try:
            with httpx.Client(timeout=10) as c:
                r = c.get(f"{settings.LOKI_API_URL}/loki/api/v1/labels")
                r.raise_for_status()
                return r.json().get("data", [])
        except Exception as e:
            return [f"error: {e}"]

    @mcp.tool(
        name="loki_label_values",
        description="查询某 label 的所有取值（如 ip / job / host）。",
    )
    def loki_label_values(label: str) -> list[str]:
        try:
            with httpx.Client(timeout=10) as c:
                r = c.get(f"{settings.LOKI_API_URL}/loki/api/v1/label/{label}/values")
                r.raise_for_status()
                return r.json().get("data", [])
        except Exception as e:
            return [f"error: {e}"]