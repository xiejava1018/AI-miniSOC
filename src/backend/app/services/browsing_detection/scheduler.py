"""
后台调度

在 FastAPI lifespan 中启动后台 asyncio task，周期性执行检测。
- start_browsing_detector() : 启动（幂等，受 BROWSING_DETECT_ENABLED 控制）
- stop_browsing_detector()  : 停止
- run_detection_once()      : 执行单轮检测（可手动触发）
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from prometheus_client import Counter

from app.core.config import settings
from app.core.database import SessionLocal, engine
from app.models.base import Base
import app.models  # noqa: F401  确保模型注册
from app.services.browsing_detection.config import get_detection_config
from app.services.browsing_detection.loki_client import LokiClient
from app.services.browsing_detection.log_parser import parse_loki_result
from app.services.browsing_detection.baseline_service import BaselineService
from app.services.browsing_detection.rule_engine import RuleEngine
from app.services.browsing_detection.event_service import EventService

logger = logging.getLogger(__name__)

# Prometheus 指标
_DETECT_RUNS = Counter(
    "browsing_detection_runs_total", "Total browsing detection runs"
)
_DETECT_ERRORS = Counter(
    "browsing_detection_errors_total", "Total browsing detection errors"
)
_LAST_RUN_SECONDS = 0.0

_detector_task: asyncio.Task | None = None

_BROWSING_TABLES = {"soc_browsing_events", "soc_browsing_blacklist", "soc_browsing_baseline"}


def _ensure_tables() -> None:
    """确保 3 张检测表已建（checkfirst，幂等）"""
    tables = [t for n, t in Base.metadata.tables.items() if n in _BROWSING_TABLES]
    Base.metadata.create_all(bind=engine, tables=tables)


async def run_detection_once() -> dict:
    """执行单轮检测，返回统计信息"""
    global _LAST_RUN_SECONDS
    db = SessionLocal()
    started = datetime.now(timezone.utc)
    stats = {"fetched": 0, "parsed": 0, "findings": 0, "events": 0, "error": None}
    _DETECT_RUNS.inc()
    try:
        config = get_detection_config(db)
        if not config.enabled:
            stats["error"] = "disabled"
            return stats

        # 检测窗口（UTC）
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=config.window_minutes)
        start_ns = int(start.timestamp() * 1_000_000_000)
        end_ns = int(end.timestamp() * 1_000_000_000)

        # 1. 拉取（同步 httpx 放到线程池，避免阻塞事件循环）
        client = LokiClient()
        try:
            streams = await asyncio.to_thread(
                client.query_range,
                '{exporter="OTLP"}',
                start_ns,
                end_ns,
                10000,
            )
        finally:
            client.close()
        stats["fetched"] = sum(len(s.get("values", [])) for s in streams)
        logger.info("browsing detection step1 fetched=%d", stats["fetched"])

        # 2. 解析
        records = parse_loki_result(streams)
        stats["parsed"] = len(records)
        if not records:
            logger.debug("窗口内无日志，跳过")
            return stats

        # 3. 基线预加载
        baseline = BaselineService(db)
        internal_ips = {r.ip for r in records if r.is_internal}
        known_map = baseline.get_known_domains_bulk(internal_ips)

        # 4. 规则评估
        engine = RuleEngine(db, config)
        findings = engine.evaluate(records, known_map, start, end)
        stats["findings"] = len(findings)

        # 5. 更新基线（仅 url 记录，仅内网）
        baseline.upsert_many([r for r in records if r.action == "url"])

        # 6. 落地 + 通知
        event_svc = EventService(db)
        created = await event_svc.create_findings(findings, config)
        stats["events"] = created

        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        _LAST_RUN_SECONDS = elapsed
        logger.info(
            "browsing detection: fetched=%d parsed=%d findings=%d events=%d (%.1fs)",
            stats["fetched"], stats["parsed"], stats["findings"], stats["events"], elapsed,
        )
    except Exception:
        _DETECT_ERRORS.inc()
        stats["error"] = "exception"
        logger.exception("browsing detection failed")
    finally:
        db.close()
    return stats


async def _detector_loop() -> None:
    """主循环：每 interval_seconds 执行一轮"""
    logger.info("browsing detector loop started")
    _ensure_tables()
    while True:
        # 动态读取间隔（配置变更生效）
        interval = 300
        try:
            db = SessionLocal()
            try:
                config = get_detection_config(db)
                interval = config.interval_seconds if config.enabled else 60
            finally:
                db.close()
        except Exception:
            logger.exception("读取检测配置失败，使用默认间隔")

        if interval > 0:
            try:
                logger.info("browsing detector loop: start round")
                await run_detection_once()
                logger.info("browsing detector loop: round done, next in %ds", interval)
            except Exception:
                logger.exception("detector loop iteration failed")
        await asyncio.sleep(max(30, interval))


def start_browsing_detector() -> None:
    """启动后台检测任务（幂等）"""
    global _detector_task
    if _detector_task is not None and not _detector_task.done():
        return
    if not settings.BROWSING_DETECT_ENABLED:
        logger.info("browsing detector disabled by BROWSING_DETECT_ENABLED")
        return
    _ensure_tables()
    _detector_task = asyncio.create_task(_detector_loop())
    logger.info("browsing detector task started")


async def stop_browsing_detector() -> None:
    """停止后台检测任务"""
    global _detector_task
    if _detector_task and not _detector_task.done():
        _detector_task.cancel()
        try:
            await _detector_task
        except asyncio.CancelledError:
            pass
    _detector_task = None
    logger.info("browsing detector task stopped")
