"""
AI-miniSOC 数据同步客户端

负责推送采集数据到 AI-miniSOC、健康检查、重试和错误处理。
注意：AI-miniSOC 的 ResponseWrapperMiddleware 会将响应包装为
{"code": 200, "msg": "success", "data": {...}}，需从 data 字段提取实际响应。
"""

import asyncio
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class MiniSOCClient:
    """AI-miniSOC 数据同步客户端"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        self.max_retries = max_retries

    async def sync(
        self,
        source: str,
        data_type: str,
        items: list[dict],
        metadata: Optional[dict] = None,
    ) -> dict:
        """推送采集数据到 AI-miniSOC"""
        payload = {
            "source": source,
            "data_type": data_type,
            "items": items,
        }
        if metadata:
            payload["metadata"] = metadata

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await self.client.post(
                    f"{self.base_url}/api/v1/data/sync",
                    json=payload,
                )
                resp.raise_for_status()

                # 解包中间件包装的响应: {code, msg, data}
                body = resp.json()
                if body.get("code") == 200 and "data" in body:
                    result = body["data"]
                else:
                    result = body

                logger.info(
                    f"同步成功: source={source}, type={data_type}, "
                    f"total={result.get('total')}, created={result.get('created')}, "
                    f"updated={result.get('updated')}, skipped={result.get('skipped')}"
                )
                return result

            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(
                    f"同步失败 (attempt {attempt}/{self.max_retries}): "
                    f"status={e.response.status_code}, body={e.response.text[:200]}"
                )
            except httpx.RequestError as e:
                last_error = e
                logger.warning(f"网络错误 (attempt {attempt}/{self.max_retries}): {e}")

            if attempt < self.max_retries:
                await asyncio.sleep(2 ** attempt)

        raise RuntimeError(f"同步失败，重试 {self.max_retries} 次后放弃: {last_error}")

    async def health_check(self) -> bool:
        """检查 AI-miniSOC 是否可达"""
        try:
            resp = await self.client.get(f"{self.base_url}/api/v1/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        await self.client.aclose()
