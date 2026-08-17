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
from app.core.database import SessionLocal
import app.models  # noqa: F401  确保模型注册
from app.services.browsing_detection.config import get_detection_config
from app.services.browsing_detection.loki_client import LokiClient
from app.services.browsing_detection.log_parser import parse_loki_result
from app.services.browsing_detection.baseline_service import BaselineService
from app.services.browsing_detection.rule_engine import RuleEngine
from app.services.browsing_detection.event_service import EventService
from app.services.task_observability import track_task

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

# P1-T2：原 _ensure_tables / Base.metadata.create_all 已迁移化（迁移 e2f3a4b5c6d7 / f3a4b5c6d7e8），
# 生产启动路径不再有运行时 DDL。
_BROWSING_TABLES_DEPRECATED = {"soc_browsing_events", "soc_browsing_blacklist", "soc_browsing_baseline"}


@track_task(
    task_key="browsing_detector",
    task_name="上网行为检测",
    task_type="scheduled",
    schedule_expr="@every 5m",
    expected_interval_s=300,
    timeout_s=600,
    source_key="loki:browsing",
)
async def run_detection_once() -> dict:
    """执行单轮检测，返回统计信息"""
    global _LAST_RUN_SECONDS
    from app.services.task_observability import update_progress_stage
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
        update_progress_stage("fetch", processed=0, total=5)
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
        update_progress_stage(
            "parse", processed=1, total=5,
            extra={"fetched": stats["fetched"]},
        )
        records = parse_loki_result(streams)
        stats["parsed"] = len(records)
        if not records:
            update_progress_stage("done", processed=5, total=5, extra=stats)
            logger.debug("窗口内无日志，跳过")
            return stats

        # 3. 基线预加载
        update_progress_stage(
            "baseline", processed=2, total=5,
            extra={"parsed": stats["parsed"]},
        )
        baseline = BaselineService(db)
        internal_ips = {r.ip for r in records if r.is_internal}
        known_map = baseline.get_known_domains_bulk(internal_ips)

        # 4. 规则评估
        update_progress_stage(
            "evaluate", processed=3, total=5,
            extra={"internal_ips": len(internal_ips)},
        )
        engine = RuleEngine(db, config)
        findings = engine.evaluate(records, known_map, start, end)
        stats["findings"] = len(findings)

        # 5. 更新基线（仅 url 记录，仅内网）
        update_progress_stage(
            "persist", processed=4, total=5,
            extra={"findings": stats["findings"]},
        )
        baseline.upsert_many([r for r in records if r.action == "url"])

        # 6. 落地 + 通知
        event_svc = EventService(db)
        created = await event_svc.create_findings(findings, config)
        stats["events"] = created

        update_progress_stage(
            "done", processed=5, total=5, extra=stats,
        )

        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        _LAST_RUN_SECONDS = elapsed
        # P2-T3：上报成功到 soc_source_health
        try:
            from app.services.source_health import SourceHealthRecorder
            SourceHealthRecorder(db).record_success(
                source_key="loki:browsing_detection",
                source_type="loki",
                display_name="上网行为检测（Loki）",
                records_count=stats["fetched"],
                expected_interval_seconds=config.interval_seconds,
            )
            db.commit()
        except Exception:
            logger.exception("写 soc_source_health 失败")
            db.rollback()
        logger.info(
            "browsing detection: fetched=%d parsed=%d findings=%d events=%d (%.1fs)",
            stats["fetched"], stats["parsed"], stats["findings"], stats["events"], elapsed,
        )
    except Exception as e:
        _DETECT_ERRORS.inc()
        stats["error"] = "exception"
        logger.exception("browsing detection failed")
        # P2-T3：上报失败到 soc_source_health
        try:
            from app.services.source_health import SourceHealthRecorder
            recorder = SourceHealthRecorder(db)
            # 重设区间为默认 300
            recorder.record_failure(
                source_key="loki:browsing_detection",
                source_type="loki",
                error=f"{type(e).__name__}: {e}",
                display_name="上网行为检测（Loki）",
            )
            db.commit()
        except Exception:
            logger.exception("写 soc_source_health 失败")
            try:
                db.rollback()
            except Exception:
                pass
    finally:
        db.close()
    return stats


async def _detector_loop() -> None:
    """主循环：每 interval_seconds 执行一轮"""
    logger.info("browsing detector loop started")
    # P1-T2：原 _ensure_tables() 已移除，表由迁移 f3a4b5c6d7e8 保障
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
    # P1-T2：原 _ensure_tables() 已移除，表由迁移 f3a4b5c6d7e8 保障
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
