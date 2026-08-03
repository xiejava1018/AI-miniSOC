"""
Loki API 客户端

封装 /loki/api/v1/query_range 查询，返回解析后的日志流。
"""

import logging
from typing import List

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class LokiClient:
    """Loki 查询客户端（同步 httpx）"""

    def __init__(self, base_url: str | None = None, timeout: float = 30.0) -> None:
        self.base_url = (base_url or settings.LOKI_API_URL).rstrip("/")
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
        )

    def query_range(
        self,
        query: str,
        start_ns: int,
        end_ns: int,
        limit: int = 10000,
        direction: str = "forward",
    ) -> List[dict]:
        """
        GET /loki/api/v1/query_range

        返回流列表，每个元素形如:
            {"stream": {"ip":"192.168.0.8", "exporter":"OTLP"},
             "values": [[ts_ns, json_line], ...]}

        Args:
            start_ns / end_ns: 纳秒级 Unix 时间戳
            direction: forward(默认) / backward
        """
        try:
            resp = self._client.get(
                "/loki/api/v1/query_range",
                params={
                    "query": query,
                    "start": str(start_ns),
                    "end": str(end_ns),
                    "limit": limit,
                    "direction": direction,
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

    def close(self) -> None:
        self._client.close()
