"""行为画像 MCP tools（方案 §9.6）

让「192.168.0.8 最近有什么异常行为？」类自然语言查询直接消费画像快照。
只读快照表，不做实时 Loki 拉取（成本高；实时引导用 loki_query_range）。
"""
from __future__ import annotations

import logging

from app.core.database import SessionLocal
from app.services.behavior_profile import service as bp_service

logger = logging.getLogger(__name__)


def register(mcp) -> None:
    @mcp.tool(
        name="get_behavior_profile",
        description=(
            "获取某 IP 的行为画像聚合（活跃时段/行为节律/兴趣分类/画像标签/域名 TOP）。"
            "数据来自每日快照（留存 ≥180 天），gap 日表示数据缺失。"
        ),
    )
    def get_behavior_profile(ip: str, days: int = 7) -> dict:
        """
        Args:
            ip: 内网 IP，如 192.168.0.8
            days: 聚合窗口（1-30 天）
        """
        db = SessionLocal()
        try:
            data = bp_service.get_profile(db, ip, days)
            if data is None:
                return {"error": f"该 IP 无画像快照: {ip}（主体未纳管或快照任务未覆盖）"}
            return data
        except Exception as e:
            logger.warning("get_behavior_profile failed: %s", e)
            return {"error": str(e)}
        finally:
            db.close()

    @mcp.tool(
        name="get_behavior_profiles",
        description="获取全部画像主体摘要列表，支持按流量类型（human/machine/mixed）过滤。",
    )
    def get_behavior_profiles(traffic_type: str = "", limit: int = 50) -> dict:
        """
        Args:
            traffic_type: 留空取全部；human=人类 / machine=机器 / mixed=混合
            limit: 最大返回条数
        """
        db = SessionLocal()
        try:
            items = bp_service.get_profiles_summary(
                db, traffic_type=traffic_type or None, limit=min(limit, 500)
            )
            return {"total": len(items), "items": items}
        except Exception as e:
            logger.warning("get_behavior_profiles failed: %s", e)
            return {"error": str(e), "items": []}
        finally:
            db.close()
