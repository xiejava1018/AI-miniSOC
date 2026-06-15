"""
结构化日志配置

支持:
- JSON 格式输出 (用于日志聚合系统如 Loki, ELK)
- trace_id 字段 (用于请求链路追踪)
- 与 loguru 集成
"""

import json
import logging
import sys
import uuid
from datetime import datetime
from contextvars import ContextVar
from typing import Optional

# Context variable for trace_id propagation across async tasks
trace_id_var: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)


def get_trace_id() -> Optional[str]:
    """获取当前 trace_id"""
    return trace_id_var.get()


def set_trace_id(trace_id: Optional[str] = None) -> str:
    """设置 trace_id, 如果未提供则自动生成"""
    tid = trace_id or str(uuid.uuid4())
    trace_id_var.set(tid)
    return tid


class StructuredJsonFormatter(logging.Formatter):
    """
    结构化 JSON 日志格式化器

    输出字段:
    - timestamp: ISO 8601 格式时间戳
    - level: 日志级别 (INFO, WARNING, ERROR, etc.)
    - message: 日志消息
    - trace_id: 链路追踪 ID (如果有)
    - module: 模块名称
    - function: 函数名
    - line: 行号
    - extra: 额外字段
    """

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 添加 trace_id
        trace_id = get_trace_id()
        if trace_id:
            log_data["trace_id"] = trace_id

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # 添加 extra 字段
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)

        return json.dumps(log_data, ensure_ascii=False)


def setup_structured_logging(
    level: int = logging.INFO,
    include_trace_id: bool = True,
) -> None:
    """
    配置结构化 JSON 日志

    Args:
        level: 日志级别
        include_trace_id: 是否包含 trace_id 字段
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # 清除现有 handlers
    root_logger.handlers.clear()

    # 创建 JSON handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())
    handler.setLevel(level)

    root_logger.addHandler(handler)

    # 减少第三方库噪音 (可选)
    for logger_name in ["uvicorn", "uvicorn.access", "httpx", "httpcore"]:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    获取结构化日志记录器

    用法:
        logger = get_logger(__name__)
        logger.info("操作成功", extra={"user_id": 123, "action": "login"})
    """
    return logging.getLogger(name)


class LogContext:
    """
    日志上下文管理器,用于自动设置和清理 trace_id

    用法:
        with LogContext(request_id):
            logger.info("处理请求")
            # trace_id 自动传递
    """

    def __init__(self, trace_id: Optional[str] = None):
        self.trace_id = trace_id or str(uuid.uuid4())
        self._token: Optional[object] = None

    def __enter__(self) -> str:
        self._token = trace_id_var.set(self.trace_id)
        return self.trace_id

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._token is not None:
            trace_id_var.reset(self._token)
        return None