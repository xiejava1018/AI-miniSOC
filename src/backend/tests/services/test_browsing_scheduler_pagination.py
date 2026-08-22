"""P4 WO-1：调度检测 Loki 分页接线单测

验收锚点（2026-08-22-p4-remaining-gaps-execution-plan.md WO-1）：
1. 调度检测改用 query_range_paginated（不再单次 limit=10000）
2. LokiTruncationError → 降级单次拉取保证可用性 + stats 透出 loki_truncated
3. 小数据窗口行为不变（fetched 计数一致）
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.services.browsing_detection.loki_client import LokiTruncationError
from app.services.browsing_detection import scheduler


def _stream(label, values):
    return {"stream": {"ip": label}, "values": values}


@pytest.fixture
def detection_enabled(monkeypatch):
    """绕过 DB 配置层，直接让检测启用。"""
    cfg = MagicMock()
    cfg.enabled = True
    cfg.window_minutes = 60
    with patch.object(scheduler, "get_detection_config", return_value=cfg):
        yield cfg


def _run_with_mocks(detection_enabled, paginated_ret=None, paginated_exc=None,
                    query_range_ret=None, parse_ret=()):
    """跑 run_detection_once，mock 掉 Loki 拉取与后续解析/落库步骤。"""
    fake_streams = paginated_ret[0] if paginated_ret else []
    with patch.object(
        scheduler.LokiClient, "query_range_paginated",
        return_value=paginated_ret or ([], 0, False),
        side_effect=paginated_exc if paginated_exc else None,
    ) as m_pag, patch.object(
        scheduler.LokiClient, "query_range", return_value=query_range_ret or [],
    ) as m_qr, patch.object(
        scheduler, "parse_loki_result", return_value=list(parse_ret),
    ), patch.object(
        scheduler, "SessionLocal", return_value=MagicMock(),
    ):
        # 窗口内无记录 → 提前返回，不触及基线/规则/落库
        import asyncio
        stats = asyncio.run(scheduler.run_detection_once())
    return stats, m_pag, m_qr


def test_uses_paginated_and_small_window_unchanged(detection_enabled):
    """场景 1+3：改用分页拉取；小窗口 fetched 计数与分页 total 一致。"""
    streams = [_stream("A", [[1, "x"], [2, "y"]])]
    stats, m_pag, m_qr = _run_with_mocks(
        detection_enabled, paginated_ret=(streams, 2, False))
    assert m_pag.called, "应调用 query_range_paginated"
    assert not m_qr.called, "正常路径不应回退单次 query_range"
    assert stats["fetched"] == 2
    assert "loki_truncated" not in stats


def test_truncation_degrades_and_signals(detection_enabled):
    """场景 2：硬上限截断 → 降级单次拉取 + stats 透出截断信号。"""
    exc = LokiTruncationError(
        fetched=500_000, limit=500_000,
        window=(datetime(2026, 8, 22, 0, 0), datetime(2026, 8, 22, 1, 0)),
    )
    degraded = [_stream("A", [[1, "x"]])]
    stats, m_pag, m_qr = _run_with_mocks(
        detection_enabled, paginated_exc=exc, query_range_ret=degraded)
    assert stats["loki_truncated"] is True
    assert stats["loki_total_values"] == 500_000
    assert m_qr.called, "截断后应降级单次拉取保证检测不中断"
    assert stats["fetched"] == 1, "降级路径用已拉取流继续解析"


def test_paginated_truncated_flag_consumed(detection_enabled):
    """分页返回 truncated=True（未抛异常的边界）→ 同样透出信号。"""
    streams = [_stream("A", [[1, "x"]])]
    stats, _, m_qr = _run_with_mocks(
        detection_enabled, paginated_ret=(streams, 1, True))
    assert stats["loki_truncated"] is True
    assert stats["loki_total_values"] == 1
    assert not m_qr.called, "truncated=True 但未抛异常时无需降级"
