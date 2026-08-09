"""告警管理 MCP tools：Wazuh 告警查询。"""
from __future__ import annotations

from app.mcp.tools.base import call_api


def register(mcp) -> None:
    @mcp.tool(
        name="list_alerts",
        description=(
            "查询 Wazuh 告警列表。支持按等级 (level)、agent_id、ip 过滤，"
            "可指定时间范围（hours，默认最近 24 小时）、分页和排序。"
        ),
    )
    def list_alerts(
        skip: int = 0,
        limit: int = 50,
        level: int = 0,
        agent_id: str = "",
        ip: str = "",
        hours: int = 24,
        sort_by: str = "",
        sort_order: str = "",
    ) -> dict:
        params: dict = {"skip": skip, "limit": min(limit, 500), "hours": hours}
        if level and level > 0:
            params["level"] = level
        if agent_id:
            params["agent_id"] = agent_id
        if ip:
            params["ip"] = ip
        if sort_by:
            params["sort_by"] = sort_by
        if sort_order in ("asc", "desc"):
            params["sort_order"] = sort_order
        return call_api("GET", "/alerts", params=params)

    @mcp.tool(
        name="get_alert_detail",
        description="根据告警 ID 获取告警详情。",
    )
    def get_alert_detail(alert_id: str) -> dict:
        return call_api("GET", f"/alerts/{alert_id}")

    @mcp.tool(
        name="get_alert_stats",
        description="获取告警统计概览（按等级 / 时间窗口聚合）。",
    )
    def get_alert_stats(hours: int = 24) -> dict:
        return call_api("GET", "/alerts/stats", params={"hours": hours})

    @mcp.tool(
        name="list_alert_groups",
        description=(
            "将原始告警按 (规则, 资产) 聚合为有限个'告警簇'，按数量降序返回 TopN。"
            "这是告警治理的核心视图：让你一句话看清'过去 N 小时有哪些告警簇、各多少条、涉及哪些资产'，"
            "而不必面对百万条原始告警。"
        ),
    )
    def list_alert_groups(
        hours: int = 24,
        min_count: int = 1,
        level: int = 0,
        limit: int = 20,
    ) -> dict:
        params: dict = {"hours": hours, "min_count": min_count, "limit": min(limit, 100)}
        if level and level > 0:
            params["level"] = level
        return call_api("GET", "/alerts/groups", params=params)

    @mcp.tool(
        name="get_alert_group",
        description=(
            "查看单个告警簇的明细：样本告警、等级/时间分布、攻击者源 IP、关联资产。"
            "fingerprint 来自 list_alert_groups 返回的 fingerprint 字段（格式 'rule_id|agent_id'）。"
        ),
    )
    def get_alert_group(fingerprint: str, hours: int = 24, sample_size: int = 5) -> dict:
        params: dict = {"hours": hours, "sample_size": min(sample_size, 20)}
        return call_api("GET", f"/alerts/groups/{fingerprint}", params=params)

    @mcp.tool(
        name="get_alert_digest",
        description=(
            "获取每日告警治理摘要（最新一条，或按 date=YYYY-MM-DD 取当天）。"
            "摘要包含：原始告警总数、归并后的告警簇、高频资产、趋势、自然语言总结。"
            "设置 generate=true 会先生成再返回（适合'今天最该处理什么'这类问题）。"
        ),
    )
    def get_alert_digest(date: str = "", generate: bool = False, hours: int = 24) -> dict:
        if generate:
            return call_api("POST", "/alerts/digest/generate", params={"hours": hours}, timeout=60)
        params: dict = {}
        if date:
            params["date"] = date
        return call_api("GET", "/alerts/digest", params=params)

    @mcp.tool(
        name="list_alert_triage_top",
        description=(
            "今日必处理清单：对过去 N 小时内的 TopN 告警簇做 AI 研判，"
            "按优先级 P0>P1>P2>P3 排序返回每条簇的 verdict（优先级/是否噪声/置信度/理由/处置建议/是否建议建事件）。"
            "这是'今天最该处理什么'的直接答案，适合一线分析师或 Agent 一句话问出处置重点。"
            "AI 不可用时自动降级为启发式 verdict（source=heuristic）。"
        ),
    )
    def list_alert_triage_top(
        hours: int = 24,
        top_n: int = 0,
        force_refresh: bool = False,
    ) -> dict:
        params: dict = {"hours": hours, "force_refresh": force_refresh}
        if top_n and top_n > 0:
            params["top_n"] = min(top_n, 100)
        # 研判可能较慢（多簇并发 AI 调用），加大超时
        return call_api("GET", "/alerts/groups/triage-top", params=params, timeout=120)

    @mcp.tool(
        name="ai_triage_alert_group",
        description=(
            "对单个告警簇做 AI 研判：输出该簇的结构化结论——优先级(P0-P3)、是否噪声、"
            "置信度、研判理由、处置建议、是否建议建事件。fingerprint 来自 list_alert_groups"
            "返回的 fingerprint 字段（格式 'rule_id|agent_id'）。force_refresh=true 忽略缓存重新研判。"
        ),
    )
    def ai_triage_alert_group(
        fingerprint: str,
        hours: int = 24,
        force_refresh: bool = False,
    ) -> dict:
        params: dict = {"hours": hours, "force_refresh": force_refresh}
        return call_api(
            "POST", f"/alerts/groups/{fingerprint}/triage", params=params, timeout=60
        )