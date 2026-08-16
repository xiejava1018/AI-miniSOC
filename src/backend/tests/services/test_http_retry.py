"""P3-T1：HTTP 重试（tenacity）单测"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import httpx
import pytest

from app.core.http_retry import (
    RetryConfig,
    RetryStats,
    _is_retryable_http,
    http_retry,
)


def test_is_retryable_http_5xx():
    """5xx 应被识别为可重试。"""
    exc = httpx.HTTPStatusError(
        "Server Error", request=MagicMock(), response=MagicMock(status_code=503)
    )
    assert _is_retryable_http(exc) is True


def test_is_retryable_http_4xx():
    """4xx 应被识别为不可重试（业务错误，重试无意义）。"""
    exc = httpx.HTTPStatusError(
        "Not Found", request=MagicMock(), response=MagicMock(status_code=404)
    )
    assert _is_retryable_http(exc) is False


def test_is_retryable_http_connect_error():
    """连接错误可重试。"""
    exc = httpx.ConnectError("Connection refused")
    assert _is_retryable_http(exc) is True


def test_is_retryable_http_timeout():
    """超时可重试。"""
    exc = httpx.ReadTimeout("timeout")
    assert _is_retryable_http(exc) is True


def test_is_retryable_http_value_error():
    """非网络异常不重试。"""
    assert _is_retryable_http(ValueError("bad data")) is False


def test_retry_decorator_retries_on_5xx(monkeypatch):
    """5xx 第 N 次后成功：装饰器应重试 N-1 次。"""
    cfg = RetryConfig(max_attempts=3, initial_wait=0.01, max_wait=0.05)
    stats = RetryStats()

    call_count = {"n": 0}

    @http_retry(config=cfg, stats=stats)
    def f():
        call_count["n"] += 1
        if call_count["n"] < 3:
            resp = MagicMock(status_code=503)
            raise httpx.HTTPStatusError("Server Error", request=MagicMock(), response=resp)
        return "ok"

    result = f()
    assert result == "ok"
    assert call_count["n"] == 3
    assert stats.attempts == 3
    assert stats.retried == 2


def test_retry_decorator_does_not_retry_4xx():
    """4xx 不重试（raise_for_status 直接抛）。"""
    cfg = RetryConfig(max_attempts=3, initial_wait=0.01, max_wait=0.05)
    call_count = {"n": 0}

    @http_retry(config=cfg)
    def f():
        call_count["n"] += 1
        resp = MagicMock(status_code=404)
        raise httpx.HTTPStatusError("Not Found", request=MagicMock(), response=resp)

    try:
        f()
        assert False, "should have raised"
    except httpx.HTTPStatusError:
        pass
    assert call_count["n"] == 1


def test_retry_decorator_raises_after_max_attempts():
    """超过 max_attempts 应抛最后一次异常。"""
    cfg = RetryConfig(max_attempts=2, initial_wait=0.01, max_wait=0.05)
    call_count = {"n": 0}

    @http_retry(config=cfg)
    def f():
        call_count["n"] += 1
        resp = MagicMock(status_code=503)
        raise httpx.HTTPStatusError("Server Error", request=MagicMock(), response=resp)

    try:
        f()
        assert False, "should have raised"
    except httpx.HTTPStatusError:
        pass
    assert call_count["n"] == 2


def test_retry_config_default():
    """默认配置 3 次尝试，1-30s 退避。"""
    cfg = RetryConfig.default()
    assert cfg.max_attempts == 3
    assert cfg.initial_wait == 1.0
    assert cfg.max_wait == 30.0


def test_retry_config_for_heavy_query():
    """大查询专用配置：max_attempts=2。"""
    cfg = RetryConfig.for_heavy_query()
    assert cfg.max_attempts == 2  # 避免大查询重试放大负载