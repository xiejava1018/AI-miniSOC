"""
Loki API 客户端

封装 /loki/api/v1/query_range 与 /loki/api/v1/query 查询。

P1-T3：query_range 增加时间分片翻页 + 硬上限 + 截断信号透出；
query() 鼓励用于聚合下推（sum by / topk / count_over_time）。
"""
import logging
from datetime import datetime, timedelta
from typing import List, Tuple

import httpx

from app.core.config import settings
from app.core.http_retry import RetryConfig, RetryStats, http_retry
from app.core.time_utils import (
    UTC,
    NS_PER_SECOND,
    datetime_to_loki_ns,
    ensure_utc,
    loki_ns_to_datetime,
    split_time_window,
)

logger = logging.getLogger(__name__)

# 默认分片大小：1 小时。Loki 单次查询 1 万行限制按数据密度决定实际命中行数；
# 时间分片保证跨窗口能拉到全部明细，并透出截断信号。
DEFAULT_PAGE_STEP = timedelta(hours=1)
# 硬上限：单次分页拉取的最大流数（含各 stream 的全部 values 行）
HARD_RESULT_LIMIT = 500_000


class LokiTruncationError(RuntimeError):
    """Loki 查询被硬上限截断（信号透出给上层，详见 P1-T3）。"""

    def __init__(self, fetched: int, limit: int, window: Tuple[datetime, datetime]):
        self.fetched = fetched
        self.limit = limit
        self.window = window
        super().__init__(
            f"Loki query truncated: fetched={fetched}, limit={limit}, "
            f"window=[{window[0].isoformat()}, {window[1].isoformat()})"
        )


class LokiClient:
    """Loki 查询客户端（同步 httpx，P3-T1 加重试）"""

    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = (base_url or settings.LOKI_API_URL).rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
        )
        # P3-T1：默认重试配置
        self._retry_stats = RetryStats()
        self._retry_default = RetryConfig.default()
        self._retry_heavy = RetryConfig.for_heavy_query()

    def query_range(
        self,
        query: str,
        start_ns: int,
        end_ns: int,
        limit: int = 10000,
        direction: str = "forward",
        step: str | None = None,
    ) -> List[dict]:
        """
        GET /loki/api/v1/query_range（单次查询）

        返回流列表，每个元素形如:
            {"stream": {"ip":"192.168.0.8", "exporter":"OTLP"},
             "values": [[ts_ns, json_line], ...]}

        注意：本方法只发一次 HTTP 请求，**不**做时间分片翻页。
        需要全量明细请使用 query_range_paginated()。
        """
        try:
            resp = self._send_query_range(
                "/loki/api/v1/query_range",
                params={
                    "query": query,
                    "start": str(start_ns),
                    "end": str(end_ns),
                    "limit": limit,
                    "direction": direction,
                    **({"step": step} if step else {}),
                },
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPError as e:
            logger.error("Loki 查询失败: %s query=%s", e, query)
            raise

        if payload.get("status") != "success":
            logger.warning("Loki 返回非 success: %s", payload)
            return []

        result = payload.get("data", {}).get("result", [])
        return result if isinstance(result, list) else []

    def query_range_paginated(
        self,
        query: str,
        start_ns: int,
        end_ns: int,
        *,
        page_step: timedelta = DEFAULT_PAGE_STEP,
        page_limit: int = 10000,
        hard_limit: int = HARD_RESULT_LIMIT,
        direction: str = "forward",
    ) -> Tuple[List[dict], int, bool]:
        """P1-T3：按时间分片翻页拉取全部明细（**左闭右开**窗口）。

        Loki query_range 响应无 next 游标，只能按时间边界推进。本方法把 [start, end)
        按 page_step 切成多个子窗口，每片独立查询；累计返回流列表；超硬上限抛
        LokiTruncationError（带截断行数与窗口范围）。

        Returns:
            (results, total_values, truncated)
            - results: 合并后的流列表（每个流含各分片贡献的 values）
            - total_values: 累计的 values 行数
            - truncated: 是否触发硬上限（True 时建议改用聚合下推）

        Raises:
            LokiTruncationError: 当累计行数 ≥ hard_limit 时抛出，包含截断行数与
                触发截断的子窗口范围，便于上层观测/重试决策。
        """
        start_dt = loki_ns_to_datetime(start_ns)
        end_dt = loki_ns_to_datetime(end_ns)
        if start_dt >= end_dt:
            return [], 0, False

        merged: dict[tuple, dict] = {}  # key: tuple(stream) → {stream, values}
        total_values = 0
        truncated_at: Tuple[datetime, datetime] | None = None

        for sub_s, sub_e in split_time_window(start_dt, end_dt, step=page_step):
            sub_results = self.query_range(
                query=query,
                start_ns=datetime_to_loki_ns(sub_s),
                end_ns=datetime_to_loki_ns(sub_e),
                limit=page_limit,
                direction=direction,
            )
            for stream_obj in sub_results:
                stream_key = tuple(sorted(stream_obj.get("stream", {}).items()))
                values = stream_obj.get("values", []) or []
                if stream_key in merged:
                    merged[stream_key]["values"].extend(values)
                else:
                    merged[stream_key] = {
                        "stream": stream_obj.get("stream", {}),
                        "values": list(values),
                    }
                total_values += len(values)
                if total_values >= hard_limit:
                    truncated_at = (sub_s, sub_e)
                    break
            if truncated_at is not None:
                break

        results = list(merged.values())
        if truncated_at is not None:
            # 透出截断信号（P1-T3 验收：调用方能感知"样本不完整"）
            logger.warning(
                "Loki query truncated: fetched=%d limit=%d at window=%s",
                total_values, hard_limit, truncated_at,
            )
            raise LokiTruncationError(total_values, hard_limit, truncated_at)

        return results, total_values, False

    def query(self, query: str, time_ns: int | None = None) -> List[dict]:
        """GET /loki/api/v1/query（瞬时查询），返回 vector 列表

        用于聚合统计（sum by / topk / count_over_time 等的当前值）。
        P1-T3 鼓励优先用本方法做聚合下推，明细只在命中后按需拉取。
        """
        import time as _time
        if time_ns is None:
            time_ns = int(_time.time() * NS_PER_SECOND)
        try:
            resp = self._send_query_heavy(
                "/loki/api/v1/query",
                params={"query": query, "time": str(time_ns)},
            )
            resp.raise_for_status()
            payload = resp.json()
        except httpx.HTTPError as e:
            logger.error("Loki 瞬时查询失败: %s query=%s", e, query)
            raise
        if payload.get("status") != "success":
            return []
        result = payload.get("data", {}).get("result", [])
        return result if isinstance(result, list) else []

    # ─────────────────────────────────────────────────
    # P3-T1：底层发送重试方法
    # ─────────────────────────────────────────────────

    @http_retry(config=RetryConfig.default(), stats=RetryStats())
    def _send_query_range(self, path, params):
        """P3-T1：单次 query_range，5xx/超时重试。"""
        return self._client.get(path, params=params)

    @http_retry(config=RetryConfig.for_heavy_query(), stats=RetryStats())
    def _send_query_heavy(self, path, params):
        """P3-T1：重查询路径，重试上限 2 防放大负载。"""
        return self._client.get(path, params=params)

    @http_retry(config=RetryConfig.default(), stats=RetryStats())
    def _send_query(self, path, params):
        """P3-T1：query 路径，默认重试。"""
        return self._client.get(path, params=params)

    def close(self) -> None:
        self._client.close()