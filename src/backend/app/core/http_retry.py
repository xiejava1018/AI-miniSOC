"""
HTTP 重试装饰器（P3-T1）

为 Loki / OpenSearch / Wazuh 客户端的 httpx 调用提供统一重试装饰器：
- 区分 5xx/超时（可重试）与 4xx（不重试）
- 指数退避（wait_exponential）
- 大查询加重试上限（max_query_attempts 不同于普通 max_attempts）
- 重试统计暴露给上层（P3-T1 验收）

用法：
    from app.core.http_retry import http_retry, RetryConfig

    @http_retry(config=RetryConfig.default())
    def fetch():
        resp = httpx.get(...)
"""
import logging
from functools import wraps
from typing import Callable, Optional, TypeVar

import httpx
from tenacity import (
    RetryError,
    Retrying,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryStats:
    """单次重试统计（供上层读取）。"""
    def __init__(self):
        self.attempts = 0
        self.retried = 0

    def __repr__(self):
        return f"RetryStats(attempts={self.attempts}, retried={self.retried})"


def _is_retryable_http(exc: BaseException) -> bool:
    """判断异常是否可重试：5xx 与网络错误可重试；4xx 不重试。

    注：httpx.HTTPStatusError 在 raise_for_status() 时抛出；HTTPError 含连接/超时。
    """
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    if isinstance(exc, (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout,
                        httpx.PoolTimeout, httpx.RemoteProtocolError, httpx.NetworkError)):
        return True
    return False


class RetryConfig:
    """重试配置。"""

    def __init__(
        self,
        *,
        max_attempts: int = 3,
        initial_wait: float = 1.0,
        max_wait: float = 30.0,
        retry_4xx: bool = False,  # 默认不重试 4xx（业务错误）
    ) -> None:
        self.max_attempts = max_attempts
        self.initial_wait = initial_wait
        self.max_wait = max_wait
        self.retry_4xx = retry_4xx

    @classmethod
    def default(cls) -> "RetryConfig":
        return cls(max_attempts=3, initial_wait=1.0, max_wait=30.0, retry_4xx=False)

    @classmethod
    def for_heavy_query(cls) -> "RetryConfig":
        """大查询专用：重试上限更低（避免放大负载）。"""
        return cls(max_attempts=2, initial_wait=2.0, max_wait=15.0, retry_4xx=False)

    def __repr__(self):
        return (
            f"RetryConfig(max_attempts={self.max_attempts}, "
            f"wait={self.initial_wait}~{self.max_wait}s)"
        )


def http_retry(
    config: Optional[RetryConfig] = None,
    *,
    stats: Optional[RetryStats] = None,
) -> Callable:
    """httpx 调用重试装饰器（P3-T1）。

    用法：
        @http_retry(config=RetryConfig.default())
        def fetch(...):
            ...
    """
    cfg = config or RetryConfig.default()
    retrying = Retrying(
        stop=stop_after_attempt(cfg.max_attempts),
        wait=wait_exponential(min=cfg.initial_wait, max=cfg.max_wait),
        retry=retry_if_exception(_is_retryable_http),
        reraise=True,
    )

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            attempts_made = 0
            try:
                for attempt in retrying:
                    with attempt:
                        attempts_made += 1
                        if stats is not None:
                            stats.attempts = attempts_made
                        result = fn(*args, **kwargs)
                        if stats is not None and attempts_made > 1:
                            stats.retried = attempts_made - 1
                        return result
            except RetryError as e:
                logger.error("HTTP retry exhausted (%s): %s", cfg, e)
                raise
            finally:
                pass  # attempts_made 已记录
        return wrapper
    return decorator