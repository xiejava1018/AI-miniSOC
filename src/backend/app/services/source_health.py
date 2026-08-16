"""
数据源健康采集（P2-T3）

统一记录各采集器/同步任务的"最近成功 / 最近失败 / 失败计数"，供仪表板与告警使用。

用法：
    from app.services.source_health import SourceHealthRecorder, is_healthy

    recorder = SourceHealthRecorder(db)
    recorder.record_success("loki:browsing_detection", source_type="loki", records=12345)
    recorder.record_failure("tplink:router_192.168.0.1", source_type="tplink_collector", error="timeout")
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.source_health import SourceHealth

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SourceHealthRecorder:
    """数据源健康记录器。线程安全（PG 行级原子 upsert）。"""

    def __init__(self, db: Session) -> None:
        self.db = db

    def record_success(
        self,
        source_key: str,
        *,
        source_type: str,
        display_name: Optional[str] = None,
        records_count: Optional[int] = None,
        expected_interval_seconds: Optional[int] = None,
    ) -> None:
        """记录一次成功。

        在已有行上原子 +1 success_count、更新 last_success_at；无行则 INSERT。
        不提交——交由调用方 commit。
        """
        now = utc_now()
        existing = self.db.get(SourceHealth, source_key)
        if existing is None:
            row = SourceHealth(
                source_key=source_key,
                source_type=source_type,
                display_name=display_name or source_key,
                last_success_at=now,
                success_count=1,
                failure_count=0,
                expected_interval_seconds=expected_interval_seconds,
                last_records_count=records_count,
                updated_at=now,
            )
            self.db.add(row)
        else:
            existing.last_success_at = now
            existing.success_count = (existing.success_count or 0) + 1
            existing.last_records_count = records_count
            if expected_interval_seconds is not None:
                existing.expected_interval_seconds = expected_interval_seconds
            if display_name:
                existing.display_name = display_name
            existing.updated_at = now
            existing.last_failure_message = None  # 成功后清空错误
        logger.debug("source_health success: %s", source_key)

    def record_failure(
        self,
        source_key: str,
        *,
        source_type: str,
        error: str,
        display_name: Optional[str] = None,
    ) -> None:
        """记录一次失败。"""
        now = utc_now()
        existing = self.db.get(SourceHealth, source_key)
        if existing is None:
            row = SourceHealth(
                source_key=source_key,
                source_type=source_type,
                display_name=display_name or source_key,
                last_failure_at=now,
                last_failure_message=error[:1000],
                failure_count=1,
                updated_at=now,
            )
            self.db.add(row)
        else:
            existing.last_failure_at = now
            existing.last_failure_message = error[:1000]
            existing.failure_count = (existing.failure_count or 0) + 1
            existing.updated_at = now
        logger.warning("source_health failure: %s err=%s", source_key, error)


def is_healthy(
    last_success_at: Optional[datetime],
    *,
    expected_interval_seconds: int,
    now: Optional[datetime] = None,
) -> bool:
    """判断采集源是否健康：last_success_at 在 expected_interval_seconds × 2 内。

    >2× 周期未更新视为"采集中断"（P2-T3 验收：仪表板标红阈值）。
    """
    if last_success_at is None:
        return False
    n = now or utc_now()
    if last_success_at.tzinfo is None:
        last_success_at = last_success_at.replace(tzinfo=timezone.utc)
    elapsed = (n - last_success_at).total_seconds()
    return elapsed <= expected_interval_seconds * 2