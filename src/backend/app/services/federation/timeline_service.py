"""资产统一事件时间线服务（P0 联邦查询编排）。

设计要点（关闭 G1）：
- 本服务为 async，但三源客户端均为同步（LokiClient/httpx.Client/SQLAlchemy Session），
  故每个适配器的阻塞调用用 ``loop.run_in_executor`` 卸载到线程池，避免阻塞事件循环。
- 各适配器内部自开 ``SessionLocal()`` 独立会话（参照 graph.py:307 独立 Session + 线程池范式）。
- 三源并发由线程池实现，而非依赖 async 客户端。

诚实性约束（§5.7）：Loki 超 7 天窗口时裁剪 start 并在 coverage_note 标注。
"""
from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from typing import List, Optional

from .adapters import LokiAdapter, OSAdapter, PGAdapter
from .schemas import (
    AssetAnchor,
    EventRecord,
    EventType,
    SourceKey,
    TimelineResult,
    decode_cursor,
    encode_cursor,
)

logger = logging.getLogger(__name__)

# 三源并发上限（与 graph.py 线程池范式一致）；延迟创建避免测试期 import 副作用
_executor: Optional[ThreadPoolExecutor] = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="federation")
    return _executor


class SourceTimeout(Exception):
    def __init__(self, source: str):
        self.source = source
        super().__init__(f"source {source} timed out")


class TimelineService:
    def __init__(self, db=None):
        # db 仅用于资产锚解析（可选）；适配器自开会话
        self._db = db

    async def get_timeline(
        self,
        anchor: AssetAnchor,
        start: datetime,
        end: datetime,
        types: Optional[List[EventType]] = None,
        limit: int = 200,
        cursor: Optional[str] = None,
    ) -> TimelineResult:
        loop = asyncio.get_running_loop()
        executor = _get_executor()

        # Loki 7 天窗口裁剪（§5.7 诚实性约束）
        coverage_note = ""
        loki_start = start
        if (end - start) > timedelta(days=7):
            loki_start = end - timedelta(days=7)
            coverage_note = "Loki 仅覆盖近 7 天，start 已裁剪至窗口内"

        # 每个适配器阻塞调用都用 run_in_executor 卸载（关闭 G1）
        pg_task = self._guarded(
            loop, executor, lambda: PGAdapter().fetch(anchor, start, end), SourceKey.PG.value, 3.0
        )
        os_task = self._guarded(
            loop, executor, lambda: OSAdapter().fetch(anchor, start, end), SourceKey.OPENSEARCH.value, 5.0
        )
        lk_task = self._guarded(
            loop, executor, lambda: LokiAdapter().fetch(anchor, loki_start, end), SourceKey.LOKI.value, 8.0
        )

        results = await asyncio.gather(pg_task, os_task, lk_task, return_exceptions=True)

        events: List[EventRecord] = []
        source_status: dict[str, str] = {}
        for name, res in zip(
            [SourceKey.PG.value, SourceKey.OPENSEARCH.value, SourceKey.LOKI.value], results
        ):
            if isinstance(res, SourceTimeout):
                source_status[name] = "timeout"
                logger.warning("时间线源 %s 超时", name)
            elif isinstance(res, Exception):
                source_status[name] = "error"
                logger.warning("时间线源 %s 异常: %s", name, res)
            else:
                source_status[name] = "empty" if not res else "ok"
                events.extend(res)

        # 类型过滤
        if types:
            allowed = {t.value for t in types}
            events = [e for e in events if e.event_type.value in allowed]

        # 按 ts 降序；同 ts 用 event_id 稳定排序
        events.sort(key=lambda e: (e.ts, e.event_id), reverse=True)

        # 游标分页
        start_idx = 0
        if cursor:
            c = decode_cursor(cursor)
            if c:
                cts, cid = c
                for i, e in enumerate(events):
                    if (e.ts, e.event_id) <= (cts, cid):
                        start_idx = i + 1
                        break
        page = events[start_idx : start_idx + limit]
        next_cursor = (
            encode_cursor(page[-1].ts, page[-1].event_id)
            if page and len(page) == limit
            else None
        )

        return TimelineResult(
            asset_id=anchor.asset_id,
            events=page,
            next_cursor=next_cursor,
            source_status=source_status,
            coverage_note=coverage_note,
        )

    async def _guarded(self, loop, executor, fn, name: str, timeout: float):
        try:
            return await asyncio.wait_for(loop.run_in_executor(executor, fn), timeout)
        except asyncio.TimeoutError:
            raise SourceTimeout(name)
