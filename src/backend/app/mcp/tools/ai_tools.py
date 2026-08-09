"""AI 分析 MCP tools：让 Agent 借助智谱 AI 解释告警 / 日志。"""
from __future__ import annotations

from app.mcp.tools.base import call_api


def register(mcp) -> None:
    @mcp.tool(
        name="ai_analyze_alert",
        description=(
            "用 AI 分析一条 Wazuh 告警，返回解释、风险评估和建议。"
            "结果会被缓存（除非 force_refresh=True）。"
        ),
    )
    def ai_analyze_alert(
        alert_id: str,
        rule_id: int = 0,
        rule_level: int = 0,
        rule_description: str = "",
        full_log: str = "",
        agent_name: str = "",
        agent_ip: str = "",
        force_refresh: bool = False,
    ) -> dict:
        body: dict = {"alert_id": alert_id, "force_refresh": force_refresh}
        if rule_id:
            body["rule_id"] = rule_id
        if rule_level:
            body["rule_level"] = rule_level
        if rule_description:
            body["rule_description"] = rule_description
        if full_log:
            body["full_log"] = full_log
        if agent_name:
            body["agent_name"] = agent_name
        if agent_ip:
            body["agent_ip"] = agent_ip
        return call_api("POST", "/ai/analyze-alert", json_body=body, timeout=60)

    @mcp.tool(
        name="ai_explain_log",
        description="用 AI 解释一段日志（自由文本，非结构化告警）。",
    )
    def ai_explain_log(log_content: str) -> dict:
        return call_api("POST", "/ai/explain", json_body={"log_content": log_content}, timeout=60)

    @mcp.tool(
        name="get_ai_analysis",
        description="获取已缓存的 AI 分析结果（按 analysis_id）。",
    )
    def get_ai_analysis(analysis_id: str) -> dict:
        return call_api("GET", f"/ai/analysis/{analysis_id}")