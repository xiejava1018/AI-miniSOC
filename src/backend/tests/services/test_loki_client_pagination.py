"""P1-T3：Loki 查询分页 / 时间分片 / 截断信号单测"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.core.time_utils import datetime_to_loki_ns, UTC
from app.services.browsing_detection.loki_client import (
    LokiClient,
    LokiTruncationError,
    HARD_RESULT_LIMIT,
    DEFAULT_PAGE_STEP,
)


def _mock_response(payload):
    """构造 httpx Response 替身"""
    resp = MagicMock()
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _success_payload(streams):
    return {"status": "success", "data": {"result": streams}}


def _stream(label, values):
    """构造 Loki 流：values=[[ts_ns, json_str], ...]"""
    return {"stream": {"ip": label}, "values": values}


def test_query_range_paginated_merges_streams_across_windows():
    """跨窗口分片：相同 stream 应合并 values；不同 stream 分别保留。"""
    client = LokiClient(base_url="http://fake")
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = start + timedelta(hours=2)  # 跨 2 小时

    # 第一小时返回 ip=A 的 3 行（mock query_range 直接返回 result list）
    page1 = [_stream("A", [[1, "a1"], [2, "a2"], [3, "a3"]])]
    # 第二小时返回 ip=A 的 2 行 + ip=B 的 1 行
    page2 = [
        _stream("A", [[4, "a4"], [5, "a5"]]),
        _stream("B", [[6, "b1"]]),
    ]

    with patch.object(client, "query_range", side_effect=[page1, page2]) as m:
        results, total, truncated = client.query_range_paginated(
            query='{ip=~"192.168.0.*"}',
            start_ns=datetime_to_loki_ns(start),
            end_ns=datetime_to_loki_ns(end),
            page_step=timedelta(hours=1),
        )

    assert truncated is False
    assert total == 6
    assert m.call_count == 2
    # 合并后应有 2 个流（A: 5 行, B: 1 行）
    by_ip = {r["stream"]["ip"]: r["values"] for r in results}
    assert len(by_ip["A"]) == 5
    assert len(by_ip["B"]) == 1


def test_query_range_paginated_empty_window():
    """空窗口（start >= end）应直接返回空，不发请求。"""
    client = LokiClient(base_url="http://fake")
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    with patch.object(client, "query_range") as m:
        results, total, truncated = client.query_range_paginated(
            query='{ip="x"}',
            start_ns=datetime_to_loki_ns(start),
            end_ns=datetime_to_loki_ns(start),  # 同 start
        )
    assert results == []
    assert total == 0
    assert truncated is False
    assert m.call_count == 0


def test_query_range_paginated_truncation_signal():
    """达到硬上限应抛 LokiTruncationError 并透出截断窗口。"""
    client = LokiClient(base_url="http://fake")
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = start + timedelta(hours=3)

    # 第 1 小时：100 行
    page1 = [_stream("A", [[i, f"a{i}"] for i in range(100)])]
    # 第 2 小时：触发硬上限（hard_limit=150）
    page2 = [_stream("A", [[i, f"a{i}"] for i in range(100)])]

    with patch.object(client, "query_range", side_effect=[page1, page2]):
        try:
            client.query_range_paginated(
                query='{ip="x"}',
                start_ns=datetime_to_loki_ns(start),
                end_ns=datetime_to_loki_ns(end),
                page_step=timedelta(hours=1),
                hard_limit=150,
            )
            assert False, "should have raised LokiTruncationError"
        except LokiTruncationError as e:
            assert e.fetched >= 150
            assert e.limit == 150
            # 截断点应在第 2 个子窗口内
            assert e.window[0] == start + timedelta(hours=1)
            assert e.window[1] == start + timedelta(hours=2)


def test_query_range_paginated_left_closed_right_open():
    """窗口切分必须左闭右开（P1-T5 协同）：[start, end) 不重叠。"""
    # 切 2.5 小时，page_step=1h → 3 段：[0,1)[1,2)[2,2.5)
    from app.core.time_utils import split_time_window
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    end = start + timedelta(hours=2, minutes=30)
    parts = split_time_window(start, end, step=timedelta(hours=1))
    assert len(parts) == 3
    assert parts[0][1] == parts[1][0]
    assert parts[1][1] == parts[2][0]
    assert parts[2][1] == end


def test_hard_limit_default_value():
    """硬上限默认 50 万。"""
    assert HARD_RESULT_LIMIT == 500_000


def test_default_page_step():
    """默认分片 1 小时。"""
    assert DEFAULT_PAGE_STEP == timedelta(hours=1)


def test_single_query_range_still_works():
    """原 query_range 单次接口仍可调用（向后兼容）。"""
    client = LokiClient(base_url="http://fake")
    payload = _success_payload([_stream("A", [[1, "x"]])])
    with patch.object(client._client, "get") as mock_get:
        mock_get.return_value = _mock_response(payload)
        out = client.query_range(query='{x="y"}', start_ns=0, end_ns=10**18)
    assert out == payload["data"]["result"]