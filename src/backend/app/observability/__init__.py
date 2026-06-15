"""
可观测性模块

导出:
- metrics: Prometheus 指标定义
- logger: 结构化日志配置
"""

from app.observability.metrics import (
    llm_request_duration,
    llm_tokens_total,
    llm_cost_usd_total,
    tool_execution_count,
    agent_process_count,
    agent_session_active,
    get_all_metrics,
)

from app.observability.logging_config import (
    setup_structured_logging,
    get_logger,
    get_trace_id,
    set_trace_id,
    LogContext,
)

__all__ = [
    # Metrics
    "llm_request_duration",
    "llm_tokens_total",
    "llm_cost_usd_total",
    "tool_execution_count",
    "agent_process_count",
    "agent_session_active",
    "get_all_metrics",
    # Logging
    "setup_structured_logging",
    "get_logger",
    "get_trace_id",
    "set_trace_id",
    "LogContext",
]