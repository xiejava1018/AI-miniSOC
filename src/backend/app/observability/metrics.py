"""
可观测性指标定义

基于 docs/plans/2026-06-15-pi-ai-integration-design.md §3.9
遵循 Prometheus 命名最佳实践:
- snake_case
- _total 后缀给 Counter
- _seconds 后缀给 Histogram
"""

from prometheus_client import Counter, Histogram, Gauge, REGISTRY

# ============================================================
# LLM 相关指标
# ============================================================

# LLM 请求持续时间 (Histogram)
llm_request_duration = Histogram(
    name="llm_request_duration_seconds",
    documentation="LLM request duration in seconds",
    labelnames=["model", "provider", "status"],
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)

# LLM Token 计数 (Counter)
llm_tokens_total = Counter(
    name="llm_tokens_total",
    documentation="Total LLM tokens used",
    labelnames=["model", "direction"],
)

# LLM 成本追踪 (Counter)
llm_cost_usd_total = Counter(
    name="llm_cost_usd_total",
    documentation="Total LLM cost in USD",
    labelnames=["model", "provider"],
)

# ============================================================
# Agent 相关指标
# ============================================================

# Agent 进程计数 (Gauge)
agent_process_count = Gauge(
    name="agent_process_count",
    documentation="Number of agent processes by role and state",
    labelnames=["role", "state"],
)

# Agent 活跃会话 (Gauge)
agent_session_active = Gauge(
    name="agent_session_active",
    documentation="Number of active agent sessions by role",
    labelnames=["role"],
)

# ============================================================
# Tool 执行指标
# ============================================================

# Tool 执行计数 (Counter)
tool_execution_count = Counter(
    name="tool_execution_count",
    documentation="Total tool executions",
    labelnames=["tool", "status"],
)


def get_all_metrics() -> dict:
    """获取所有已注册的指标 (用于调试)"""
    return {
        "llm_request_duration_seconds": llm_request_duration,
        "llm_tokens_total": llm_tokens_total,
        "llm_cost_usd_total": llm_cost_usd_total,
        "agent_process_count": agent_process_count,
        "agent_session_active": agent_session_active,
        "tool_execution_count": tool_execution_count,
    }