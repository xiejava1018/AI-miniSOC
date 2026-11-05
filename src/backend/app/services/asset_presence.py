"""资产存在性服务（P1/P2/P3 资产失联治理核心）

三条公理（2026-11-04 设计讨论）：
  1. 证据分离——传感器只报"我看到了 X"，存在性状态由证据推导
  2. 缺席需要覆盖证明——"扫过该网段但它不在结果里"才算失联证据
  3. 状态有时效——任何观测可复活（active），断言不自动过期也不自动删除

对外三个入口：
  record_observation()   任何源看到资产时调用（观测 upsert + 复活）
  record_task_coverage() 扫描任务回报完成时调用（写覆盖凭证，不结算）
  settle_coverage()      周期结算（由 presence_scheduler 驱动）：缺席计次 + 状态迁移

设计要点：
  - 结算不在 report 时同步做：采集器先 PATCH report 后才 POST /sync 发现数据
    （实测 20:08:57 report / 20:09:34 数据落地），report 时结算会把全网标失联。
    因此结算由 scheduler 延迟 ≥10min 进行，凭证 settled 标记保证幂等。
  - 阈值走配置中心 soc_system_config(category='asset_lifecycle')，缺省值兜底。
  - source 不健康期间暂停缺席结算（"我没看"≠"它不在"）——scanner 通道健康
    由数据健康层判断，此处用最近 10 分钟 scanner 通道 source_health 宽松判定。
"""

from __future__ import annotations

import ipaddress
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text as sa_text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_presence import AssetObservation, ScanCoverage

logger = logging.getLogger(__name__)

# 状态常量（避免裸字符串散落，但 alert_levels 式的独立模块对这个体量过重）
STATE_ACTIVE = "active"
STATE_UNVERIFIED = "unverified"
STATE_PRESUMED_OFFLINE = "presumed_offline"
STATE_RETIRED = "retired"

# 展示/筛选统一口径：这些存在性状态下 effective_status 视为 offline
MISSING_STATES = (STATE_UNVERIFIED, STATE_PRESUMED_OFFLINE, STATE_RETIRED)

# 结算延迟：report 后至少等这么久才结算（等 /sync 数据落地）
SETTLE_DELAY_SECONDS = 600

_DEFAULTS = {
    "miss_streak_threshold": 2,
    "offline_days": 30,
    "fail_alert_threshold": 3,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_thresholds(db: Session) -> dict:
    """读配置中心阈值（category=asset_lifecycle），失败/缺省用默认值。"""
    out = dict(_DEFAULTS)
    try:
        from app.models.system_config import SystemConfig

        rows = (
            db.query(SystemConfig)
            .filter(SystemConfig.category == "asset_lifecycle")
            .all()
        )
        for r in rows:
            if r.key in out:
                try:
                    out[r.key] = int(r.value)
                except (TypeError, ValueError):
                    pass
    except SQLAlchemyError:
        logger.warning("read asset_lifecycle config failed, using defaults", exc_info=True)
    return out


# ============================================================================
# 观测（公理 1 / 公理 3 复活）
# ============================================================================
def record_observation(
    db: Session,
    asset_id,
    source: str,
    evidence_type: str = "sync",
    observed_at: Optional[datetime] = None,
) -> None:
    """记录一次"看到了"。不 commit——事务归调用方。

    - soc_asset_observations 按 (asset_id, source) 合并心跳
    - soc_assets.last_seen_at 推进、miss_streak 清零
    - lifecycle_state 复活为 active（retired 也复活：证据优先于人，
      但 retired 的复活由人工确认语义保护——见 settle 注释）
    """
    ts = observed_at or _now()
    try:
        obs = (
            db.query(AssetObservation)
            .filter(
                AssetObservation.asset_id == asset_id,
                AssetObservation.source == source,
            )
            .first()
        )
        if obs is None:
            db.add(
                AssetObservation(
                    asset_id=asset_id, source=source,
                    evidence_type=evidence_type, last_seen_at=ts, obs_count=1,
                )
            )
        else:
            obs.last_seen_at = ts
            obs.obs_count = (obs.obs_count or 0) + 1
            obs.evidence_type = evidence_type

        asset = db.query(Asset).filter(Asset.id == asset_id).first()
        if asset is not None:
            if not asset.last_seen_at or asset.last_seen_at < ts:
                asset.last_seen_at = ts
            asset.miss_streak = 0
            # 观测复活：unverified/presumed_offline → active。
            # retired 是人工确认的终态，复活会破坏审计语义，只升级非终态。
            if asset.lifecycle_state in (STATE_UNVERIFIED, STATE_PRESUMED_OFFLINE):
                asset.lifecycle_state = STATE_ACTIVE
    except SQLAlchemyError:
        # 观测失败不阻塞主链路（采集器同步比存在性台账重要）
        logger.warning("record_observation(%s, %s) failed", asset_id, source, exc_info=True)


# ============================================================================
# 覆盖凭证（公理 2 的"我看过了"）
# ============================================================================
def record_task_coverage(db: Session, task) -> None:
    """扫描任务 report 时写覆盖凭证（每个 target 一行，含失败）。不 commit。"""
    try:
        targets = task.target_summary or []
        if not targets:
            return
        for t in targets:
            value = str(t.get("value", "")).strip()
            if not value:
                continue
            exists = (
                db.query(ScanCoverage)
                .filter(
                    ScanCoverage.task_uuid == task.task_uuid,
                    ScanCoverage.target_value == value,
                )
                .first()
            )
            if exists:
                continue
            db.add(
                ScanCoverage(
                    task_uuid=task.task_uuid,
                    mode=task.mode or "internal",
                    scope=task.scope,
                    target_value=value,
                    target_type=t.get("type"),
                    status=task.status or "unknown",
                    hosts_found=task.items_scanned if task.status == "success" else None,
                    scanned_at=task.finished_at or _now(),
                )
            )
    except SQLAlchemyError:
        logger.warning("record_task_coverage(%s) failed", getattr(task, "task_uuid", "?"), exc_info=True)


# ============================================================================
# 结算（公理 2 的"目标缺席"）
# ============================================================================
def _iter_cidr_assets(db: Session, cidr: str):
    """取网段内资产。asset_ip 是 Text，先 LIKE 粗筛再 Python 精筛（防脏数据）。"""
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError:
        return []
    # 粗筛前缀：IPv4 /24 取前三段，更宽网段取共同前两段（够用且不误杀）
    if net.version == 4:
        prefix = ".".join(str(net.network_address).split(".")[:2])
        like = f"{prefix}.%"
    else:
        like = "%"
    candidates = db.query(Asset).filter(Asset.asset_ip.like(like)).all()
    out = []
    for a in candidates:
        try:
            if ipaddress.ip_address(str(a.asset_ip)) in net:
                out.append(a)
        except ValueError:
            continue
    return out


def _scanner_channel_healthy(db: Session) -> bool:
    """scanner 通道最近 10 分钟有成功记录才结算（公理 2 的前提：我看得见）。"""
    try:
        from app.models.source_health import SourceHealth

        row = (
            db.query(SourceHealth)
            .filter(SourceHealth.source_key == "scanner:discovery")
            .order_by(SourceHealth.last_success_at.desc())
            .first()
        )
        if row is None or row.last_success_at is None:
            # 无健康记录（新环境）——默认放行，避免结算永久饿死
            return True
        return row.last_success_at >= _now() - timedelta(hours=2)
    except SQLAlchemyError:
        return True


def settle_coverage(db: Session, limit: int = 50) -> dict:
    """结算未处理的成功 internal 覆盖凭证。由 scheduler 周期调用（自建 session）。"""
    stats = {"settled": 0, "miss_marked": 0, "promoted": 0, "revived_by_timeout": 0}
    if not _scanner_channel_healthy(db):
        logger.info("presence settle skipped: scanner channel unhealthy")
        return stats

    thresholds = get_thresholds(db)
    miss_threshold = thresholds["miss_streak_threshold"]
    offline_days = thresholds["offline_days"]

    cutoff = _now() - timedelta(seconds=SETTLE_DELAY_SECONDS)
    covers = (
        db.query(ScanCoverage)
        .filter(
            ScanCoverage.settled.is_(False),
            ScanCoverage.status == "success",
            ScanCoverage.mode == "internal",
            ScanCoverage.target_type == "cidr",
            ScanCoverage.scanned_at <= cutoff,
        )
        .order_by(ScanCoverage.scanned_at.asc())
        .limit(limit)
        .all()
    )
    for cov in covers:
        # 找对应任务的扫描窗口起点：结算时"窗口内被看到"= last_seen_at >= task.started_at
        task_row = db.execute(
            sa_text("SELECT started_at FROM soc_scanner_tasks WHERE task_uuid = :u"),
            {"u": str(cov.task_uuid)},
        ).fetchone()
        window_start = task_row[0] if task_row and task_row[0] else cov.scanned_at - timedelta(hours=1)

        miss_marked = 0
        for asset in _iter_cidr_assets(db, cov.target_value):
            # retired 是人工终态，不参与缺席机器判定
            if asset.lifecycle_state == STATE_RETIRED:
                continue
            seen_in_window = (
                asset.last_seen_at is not None and asset.last_seen_at >= window_start
            )
            if seen_in_window:
                # 窗口内被看到过（observation 钩子已清零），幂等保护
                if asset.miss_streak:
                    asset.miss_streak = 0
                if asset.lifecycle_state == STATE_UNVERIFIED:
                    asset.lifecycle_state = STATE_ACTIVE
                continue
            # 缺席：计次 + 迁移
            asset.miss_streak = (asset.miss_streak or 0) + 1
            asset.last_scan_missed_at = _now()
            miss_marked += 1
            last_seen = asset.last_seen_at or asset.created_at
            if last_seen and last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            long_gone = last_seen and (_now() - last_seen) > timedelta(days=offline_days)
            if long_gone:
                # 长期无任何观测（超过 offline_days）直接疑似下线
                if asset.lifecycle_state != STATE_PRESUMED_OFFLINE:
                    asset.lifecycle_state = STATE_PRESUMED_OFFLINE
                    stats["promoted"] += 1
            elif asset.miss_streak >= miss_threshold:
                if asset.lifecycle_state != STATE_UNVERIFIED:
                    asset.lifecycle_state = STATE_UNVERIFIED
                    stats["promoted"] += 1
        cov.settled = True
        cov.settled_at = _now()
        cov.miss_marked = miss_marked
        stats["settled"] += 1
        stats["miss_marked"] += miss_marked

    if stats["settled"]:
        try:
            db.commit()
            logger.info("presence settle: %s", stats)
        except SQLAlchemyError:
            db.rollback()
            logger.exception("presence settle commit failed")
    return stats


def _maybe_alert_scan_failures(db: Session) -> None:
    """scheduled 内网扫描连续失败 ≥ 阈值 → 给 admin 发站内通知（24h 至多一条，防刷屏）。"""
    try:
        streak, last_success = consecutive_scan_failures(db)
        threshold = get_thresholds(db)["fail_alert_threshold"]
        if streak < threshold:
            return
        from datetime import timedelta as _td
        from app.models.notification import Notification
        from app.models.user import User

        dup = (
            db.query(Notification)
            .filter(
                Notification.type == "scan_coverage",
                Notification.title.like("内网定时扫描连续失败%"),
                Notification.created_at > _now() - _td(hours=24),
            )
            .first()
        )
        if dup:
            return
        admins = db.query(User).filter(User.status == "active").all()
        content = (
            f"内网定时扫描已连续失败 {streak} 次（上次成功：{last_success or '从未'}）。"
            f"失联结算已暂停，请检查 scanner-collector 与扫描目标配置。"
        )
        for u in admins:
            db.add(Notification(
                user_id=u.id, type="scan_coverage",
                title=f"内网定时扫描连续失败 {streak} 次",
                content=content, link="/data-health",
            ))
        db.commit()
        logger.warning("scan failure alert sent: streak=%d", streak)
    except Exception:
        db.rollback()
        logger.warning("_maybe_alert_scan_failures failed", exc_info=True)


def consecutive_scan_failures(db: Session, mode: str = "internal", scope: str = "scheduled") -> tuple[int, Optional[datetime]]:
    """scheduled 内网扫描连续失败次数 + 最后一次成功时间（数据健康告警用）。"""
    row = db.execute(
        sa_text(
            "SELECT status, created_at, finished_at FROM soc_scanner_tasks"
            " WHERE mode = :m AND scope = :s AND status IN ('success','failed')"
            " ORDER BY created_at DESC LIMIT 60"
        ),
        {"m": mode, "s": scope},
    ).fetchall()
    streak = 0
    for r in row:
        if r[0] == "failed":
            streak += 1
        else:
            break
    last_success = next((r[2] or r[1] for r in row if r[0] == "success"), None)
    return streak, last_success
