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
                # 注意：业务失败时 HTTP 仍是 200，真实状态在 body.code（CLAUDE.md 注意 #11）。
                # 不能只看 HTTP 状态——否则业务失败会被记成“同步成功”（假绿）。
                body = resp.json()
                if body.get("code") == 200 and isinstance(body.get("data"), dict):
                    result = body["data"]
                elif body.get("code") and body.get("code") != 200:
                    # 业务错误（envelope 包成 HTTP 200）→ 当作失败，走重试
                    msg = body.get("msg") or body.get("detail") or str(body)[:200]
                    logger.warning(
                        f"同步被控制面拒绝 (attempt {attempt}/{self.max_retries}): "
                        f"code={body.get('code')}, msg={msg[:200]}"
                    )
                    last_error = RuntimeError(f"业务失败 code={body.get('code')}: {msg}")
                    if attempt < self.max_retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise last_error
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

    # ----------------------------------------------------------------------
    # P3 资产扫描：控制面 + 拉模型（final.md §7.4 + 附录 C）
    # ----------------------------------------------------------------------

    async def heartbeat(
        self,
        scanner_id: str,
        ip: str = None,
        version: str = None,
        capabilities: list = None,
        reachable_subnets: list = None,
        running_tasks: int = None,
    ) -> dict:
        """上报心跳。返回后端响应（含 status/last_heartbeat）。"""
        body = {"scanner_id": scanner_id}
        if ip: body["ip"] = ip
        if version: body["version"] = version
        if capabilities is not None: body["capabilities"] = capabilities
        if reachable_subnets is not None: body["reachable_subnets"] = reachable_subnets
        if running_tasks is not None: body["running_tasks"] = running_tasks
        return await self._post_json("/api/v1/scan/agents/heartbeat", body)

    async def fetch_pending(self, scanner_id: str, caps: list = None) -> list:
        """拉取可认领任务列表。

        Args:
            scanner_id: 本扫描器 ID（与 heartbeat 报名一致）
            caps: 可选能力过滤（逗号分隔，例 "internal,public"）
        Returns:
            list[dict] 任务列表（可能空）
        """
        params = {"scanner_id": scanner_id}
        if caps:
            params["caps"] = ",".join(caps)
        # GET 不走 body 且 base64 url-safe
        try:
            resp = await self.client.get(
                f"{self.base_url}/api/v1/scan/tasks/pending",
                params=params,
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") == 200:
                return (body.get("data") or {}).get("tasks", []) or []
            return []
        except Exception as e:
            logger.warning("fetch_pending failed: %s", e)
            return []

    async def claim(self, task_uuid: str, scanner_id: str) -> dict:
        """原子认领任务。返回后端响应（含 claimed / nmap_args / target_summary）。"""
        return await self._patch_json(
            f"/api/v1/scan/tasks/{task_uuid}/claim",
            {"scanner_id": scanner_id},
        )

    async def report_status(
        self,
        task_uuid: str,
        status: str,
        scanner_id: str = None,
        items_scanned: int = None,
        items_created: int = None,
        items_updated: int = None,
        items_failed: int = None,
        error_message: str = None,
        duration_ms: int = None,
    ) -> dict:
        """回写任务结果。

        Args:
            status: 'success' | 'failed' | 'cancelled'
        """
        body = {"status": status}
        if scanner_id: body["scanner_id"] = scanner_id
        if items_scanned is not None: body["items_scanned"] = items_scanned
        if items_created is not None: body["items_created"] = items_created
        if items_updated is not None: body["items_updated"] = items_updated
        if items_failed is not None: body["items_failed"] = items_failed
        if error_message: body["error_message"] = error_message
        if duration_ms is not None: body["duration_ms"] = duration_ms
        return await self._patch_json(
            f"/api/v1/scan/tasks/{task_uuid}/report", body,
        )

    async def _post_json(self, path: str, body: dict) -> dict:
        """POST JSON 统一接口（带 envelope 解包 + 错误处理）。"""
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await self.client.post(
                    f"{self.base_url}{path}", json=body,
                )
                resp.raise_for_status()
                response_body = resp.json()
                if response_body.get("code") == 200:
                    return response_body.get("data") or {}
                raise RuntimeError(
                    f"server returned code={response_body.get('code')}: "
                    f"{response_body.get('msg')}"
                )
            except (httpx.HTTPStatusError, httpx.RequestError, RuntimeError) as e:
                last_error = e
                logger.warning("POST %s failed (attempt %d/%d): %s",
                               path, attempt, self.max_retries, type(e).__name__)
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"POST {path} failed after {self.max_retries} retries: {last_error}")

    async def _patch_json(self, path: str, body: dict) -> dict:
        """PATCH JSON 统一接口（带 envelope 解包 + 错误处理）。"""
        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await self.client.patch(
                    f"{self.base_url}{path}", json=body,
                )
                resp.raise_for_status()
                response_body = resp.json()
                if response_body.get("code") == 200:
                    return response_body.get("data") or {}
                raise RuntimeError(
                    f"server returned code={response_body.get('code')}: "
                    f"{response_body.get('msg')}"
                )
            except (httpx.HTTPStatusError, httpx.RequestError, RuntimeError) as e:
                last_error = e
                logger.warning("PATCH %s failed (attempt %d/%d): %s",
                               path, attempt, self.max_retries, type(e).__name__)
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
        raise RuntimeError(f"PATCH {path} failed after {self.max_retries} retries: {last_error}")
