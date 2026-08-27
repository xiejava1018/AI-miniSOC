"""数据健康聚合 API（P3 / F1.3 v1.2 新增）

把三层数据健康收拢到一个入口。PRD 的原话是"前端统一在数据健康入口展示三者，
而非三处散落"——实际情况比"散落"更糟：source_health 与 dead_letter 此前
**从未暴露任何 API**，只有后台任务在写表，没人看得见。

三层边界（勿混淆，这是排障时判断"该找谁"的依据）：
  soc_source_health         基础设施层：采集器/同步任务还在不在工作
  soc_sync_dead_letter      数据层：同步过程中被丢弃/失败的数据
  soc_asset_reconciliations 业务层：台账与实际网络的差异
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.asset_reconciliation import STATUS_PENDING, AssetReconciliation
from app.models.scanner_models import ScannerAgent
from app.models.source_health import SourceHealth
from app.services.scanner_watchdog_scheduler import HEARTBEAT_OFFLINE_SECONDS
from app.models.sync_dead_letter import SyncDeadLetter
from app.models.sync_task import SyncTask
from app.models.user import User
from app.services.asset_reconciliation import (
    STALE_SYNC_HOURS,
    AssetReconciliationService,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _source_status(sh: SourceHealth) -> tuple[str, Optional[str]]:
    """把源健康折算成 healthy / degraded / down / unknown 四态。

    判据只用已有字段，不猜：
      从未成功过           → unknown（不是 down：可能刚部署还没跑）
      最后一次是失败       → down
      超过 3 倍预期间隔未成功 → degraded（过期）
      其余                 → healthy
    """
    if sh.last_success_at is None and sh.last_failure_at is None:
        return "unknown", "从未运行"
    if sh.last_failure_at and (
        sh.last_success_at is None or sh.last_failure_at > sh.last_success_at
    ):
        return "down", (sh.last_failure_message or "最近一次运行失败")[:200]
    interval = sh.expected_interval_seconds
    if interval and sh.last_success_at:
        deadline = sh.last_success_at + timedelta(seconds=interval * 3)
        if deadline < _utcnow():
            overdue_h = round((_utcnow() - sh.last_success_at).total_seconds() / 3600, 1)
            return "degraded", f"已 {overdue_h} 小时无成功记录（预期间隔 {interval}s）"
    return "healthy", None


@router.get("/data-health", summary="数据健康总览（源健康 + 同步死信 + 对账差异）")
async def data_health(
    dead_letter_limit: int = Query(5, ge=0, le=50, description="死信样本条数"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ---------- 第 1 层：源健康 ----------
    sources = []
    counter = {"healthy": 0, "degraded": 0, "down": 0, "unknown": 0}
    for sh in db.execute(select(SourceHealth).order_by(SourceHealth.source_key)).scalars():
        status, reason = _source_status(sh)
        counter[status] += 1
        sources.append(
            {
                "source_key": sh.source_key,
                "source_type": sh.source_type,
                "display_name": sh.display_name or sh.source_key,
                "status": status,
                "reason": reason,
                "last_success_at": _iso(sh.last_success_at),
                "last_failure_at": _iso(sh.last_failure_at),
                "last_failure_message": (sh.last_failure_message or None),
                "success_count": int(sh.success_count or 0),
                "failure_count": int(sh.failure_count or 0),
                "expected_interval_seconds": sh.expected_interval_seconds,
                "last_records_count": sh.last_records_count,
                "updated_at": _iso(sh.updated_at),
            }
        )

    # ---------- 第 2 层：同步死信 ----------
    dl_pending = (
        db.execute(
            select(func.count())
            .select_from(SyncDeadLetter)
            .where(SyncDeadLetter.resolved.is_(False))
        ).scalar()
        or 0
    )
    dl_total = db.execute(select(func.count()).select_from(SyncDeadLetter)).scalar() or 0
    dl_by_source = [
        {"source": s, "data_type": t, "count": c}
        for s, t, c in db.execute(
            select(
                SyncDeadLetter.source,
                SyncDeadLetter.data_type,
                func.count(),
            )
            .where(SyncDeadLetter.resolved.is_(False))
            .group_by(SyncDeadLetter.source, SyncDeadLetter.data_type)
            .order_by(func.count().desc())
        )
    ]
    dl_samples = []
    if dead_letter_limit:
        for d in db.execute(
            select(SyncDeadLetter)
            .where(SyncDeadLetter.resolved.is_(False))
            .order_by(SyncDeadLetter.created_at.desc())
            .limit(dead_letter_limit)
        ).scalars():
            dl_samples.append(
                {
                    "id": str(d.id),
                    "batch_id": str(d.batch_id),
                    "source": d.source,
                    "data_type": d.data_type,
                    "item_key": d.item_key,
                    "error_class": d.error_class,
                    "error_message": (d.error_message or "")[:300] or None,
                    "replay_count": d.replay_count,
                    "created_at": _iso(d.created_at),
                }
            )

    # ---------- 第 3 层：对账差异 ----------
    recon = AssetReconciliationService(db).summary()
    recon_pending_all = (
        db.execute(
            select(func.count())
            .select_from(AssetReconciliation)
            .where(AssetReconciliation.status == STATUS_PENDING)
        ).scalar()
        or 0
    )

    # ---------- 同步任务新鲜度 ----------
    last_task = db.execute(
        select(SyncTask)
        .where(SyncTask.status == "completed")
        .order_by(SyncTask.completed_at.desc().nullslast(), SyncTask.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    last_failed_task = db.execute(
        select(SyncTask)
        .where(SyncTask.status == "failed")
        .order_by(SyncTask.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    last_success_at = (
        (last_task.completed_at or last_task.created_at) if last_task else None
    )
    # 与 asset_reconciliation.STALE_SYNC_HOURS 共用同一阈值。
    # 必须一致：否则对账页说"数据不新鲜、结果可能不全"，本页却显示 healthy，
    # 两个页面互相打脸，用户不知道该信哪个。
    sync_stale = (
        last_success_at is None
        or last_success_at < _utcnow() - timedelta(hours=STALE_SYNC_HOURS)
    )

    # ---------- 第 4 层（P4-H）：scanner agent 健康汇总 ----------
    # 注意：必须 select_from 才能继续 .where()，func.count() 返回 int 不能 .filter
    scanner_total = db.execute(select(func.count()).select_from(ScannerAgent)).scalar() or 0
    scanner_online = db.execute(select(func.count()).select_from(ScannerAgent).where(ScannerAgent.status == "online")).scalar() or 0
    scanner_offline = db.execute(select(func.count()).select_from(ScannerAgent).where(ScannerAgent.status == "offline")).scalar() or 0
    scanner_disabled = db.execute(select(func.count()).select_from(ScannerAgent).where(ScannerAgent.status == "disabled")).scalar() or 0
    scanner_unknown = db.execute(select(func.count()).select_from(ScannerAgent).where(ScannerAgent.status == "unknown")).scalar() or 0
    # 上次心跳检查（与 watchdog 同步口径：> HEARTBEAT_OFFLINE_SECONDS 未跳视为延迟）
    online_overdue: list[dict] = []
    for r in db.execute(
        select(ScannerAgent).where(ScannerAgent.status == "online")
    ).scalars():
        if r.last_heartbeat and (
            datetime.now(timezone.utc) - r.last_heartbeat
        ).total_seconds() > HEARTBEAT_OFFLINE_SECONDS:
            online_overdue.append({
                "scanner_id": r.scanner_id,
                "name": r.name,
                "last_heartbeat": _iso(r.last_heartbeat),
                "overdue_seconds": int(
                    (datetime.now(timezone.utc) - r.last_heartbeat).total_seconds()
                ),
            })
    # 最近 10 分钟扫描器通道（scanner-port / scanner-discovery）的 source_health
    scanner_channel_health = [
        s for s in sources if s["source_key"].startswith("scanner")
    ]
    scanner_overall = "healthy"
    if scanner_offline > 0 or scanner_disabled > 0:
        scanner_overall = "degraded"
    if online_overdue:
        scanner_overall = "degraded"
    if any(c["status"] == "down" for c in scanner_channel_health):
        scanner_overall = "down"

    # ---------- 总体结论 ----------
    # 就绪度取三层里最差的一层。宁可显示 degraded 让人去看，
    # 也不要用平均值把一个 down 的源摊薄成"基本健康"。
    if counter["down"]:
        overall = "down"
    elif counter["degraded"] or dl_pending or recon_pending_all or sync_stale:
        overall = "degraded"
    elif counter["healthy"]:
        overall = "healthy"
    else:
        overall = "unknown"

    issues: list[str] = []
    if counter["down"]:
        issues.append(f"{counter['down']} 个数据源故障")
    if counter["degraded"]:
        issues.append(f"{counter['degraded']} 个数据源过期未更新")
    if sync_stale:
        issues.append(
            f"资产同步已超过 {STALE_SYNC_HOURS} 小时无成功记录"
            f"（最近成功：{_iso(last_success_at) or '无记录'}）"
        )
    if dl_pending:
        issues.append(f"{dl_pending} 条同步数据被丢弃待处理")
    if recon_pending_all:
        issues.append(f"{recon_pending_all} 项台账差异待处理")
    if not sources:
        issues.append("尚无任何数据源健康记录（采集链路可能未接入监控）")

    # ---------- 把 scanner 状态纳入总体 ----------
    if scanner_overall == "down" and overall != "down":
        overall = "down"
    elif scanner_overall == "degraded" and overall == "healthy":
        overall = "degraded"
    if scanner_offline > 0:
        issues.append(f"{scanner_offline} 个扫描器离线")
    if scanner_disabled > 0:
        issues.append(f"{scanner_disabled} 个扫描器已禁用")
    if online_overdue:
        issues.append(f"{len(online_overdue)} 个在线扫描器心跳延迟")

    return {
        "overall_status": overall,
        "issues": issues,
        "checked_at": _iso(_utcnow()),
        "scanners": {
            "overall": scanner_overall,
            "total": scanner_total,
            "online": scanner_online,
            "offline": scanner_offline,
            "disabled": scanner_disabled,
            "unknown": scanner_unknown,
            "online_overdue": online_overdue,
            "channel_health": scanner_channel_health,
        },
        "source_health": {
            "counter": counter,
            "total": len(sources),
            "sources": sources,
        },
        "dead_letter": {
            "pending": dl_pending,
            "total": dl_total,
            "by_source": dl_by_source,
            "samples": dl_samples,
        },
        "reconciliation": {
            "latest_run": recon,
            "pending_all_runs": recon_pending_all,
        },
        "sync_freshness": {
            "last_success_at": _iso(last_success_at),
            "stale": sync_stale,
            "stale_threshold_hours": STALE_SYNC_HOURS,
            "last_success_counts": {
                "total": last_task.total_count,
                "created": last_task.created_count,
                "updated": last_task.updated_count,
                "failed": last_task.failed_count,
            }
            if last_task
            else None,
            "last_failure_at": _iso(last_failed_task.created_at) if last_failed_task else None,
            "last_failure_message": (last_failed_task.error_message or None)
            if last_failed_task
            else None,
        },
    }
