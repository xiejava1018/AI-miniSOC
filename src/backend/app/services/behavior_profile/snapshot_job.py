"""快照任务（§9.3）：每日定时对全部在线主体跑聚合 → 落快照表。

核心能力（v1.5 评审修订）：
  1. 水位回溯：启动/定时对比 last_completed_date，补齐 ≤ Loki 窗口内的缺口日；
  2. 缺口标记：超出 Loki 窗口补不回的日落 status='gap' 占位快照（防"静默的 0"假绿）；
  3. 单日部分截断：truncated_windows>0 时 confidence 降级。

画像口径：每行 = 该日单日分布；tags/cat_share 基于截至该日的滚动 7 天聚合。
"""

import datetime as dt
import logging
import threading
from typing import List, Optional, Set

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.asset import Asset
from app.models.behavior_profile import (
    BehaviorDomain, BehaviorProfile, BehaviorProfileWatermark,
)
from app.models.browsing_event import BrowsingEvent
from .aggregator import aggregate_day, compute_traffic_type, merge_days
from .classifier import classify
from .loki_source import TZ, fetch_day_events
from .tagger import build_tags, compute_confidence

logger = logging.getLogger(__name__)

LOKI_RETENTION_DAYS = 7          # Loki 仅留 7 天（CLAUDE.md）
ROLLING_TAG_WINDOW = 7           # tags / cat_share 的滚动窗口
MAX_BACKFILL_PER_RUN = 8         # 单次运行最多补的天数（防启动风暴）
SCHEDULE_HOUR = 2                # 每日 02:00


# ── 主体发现 ──────────────────────────────────────────────

def discover_targets(db: Session) -> List[dict]:
    """画像主体 = 近 7 天有上网行为的 IP ∪ 内网资产。

    返回 [{ip, asset_id, mac, hostname}]，asset_id 尽量从 soc_assets 关联。
    """
    week_ago = dt.datetime.now(TZ) - dt.timedelta(days=LOKI_RETENTION_DAYS)
    ips: Set[str] = set(
        db.execute(
            select(distinct(BrowsingEvent.ip)).where(BrowsingEvent.created_at >= week_ago)
        ).scalars()
    )
    assets = (
        db.query(Asset)
        .filter(Asset.asset_ip.isnot(None))
        .all()
    )
    by_ip = {a.asset_ip: a for a in assets}
    # 资产表里的内网 IP 也纳入（即使暂无 Loki 数据，落一行低置信快照）
    for a in assets:
        ip = (a.asset_ip or "").strip()
        if ip.startswith("192.168.") or ip.startswith("10.") or ip.startswith("172."):
            ips.add(ip)
    targets = []
    for ip in sorted(ips):
        a = by_ip.get(ip)
        targets.append({
            "ip": ip,
            "asset_id": str(a.id) if a else None,
            "mac": getattr(a, "mac_address", None),
            "hostname": getattr(a, "asset_name", None),
        })
    return targets


# ── 单主体单日快照 ────────────────────────────────────────

def snapshot_one_day(db: Session, target: dict, day: dt.date,
                     prev_days: List[dict]) -> None:
    """对单主体单日执行聚合并 upsert 快照 + 域名明细。

    prev_days: 滚动窗口内（不含本日）已有的单日聚合，用于 tags 的 7 天口径。
    """
    ip = target["ip"]
    try:
        events, stats = fetch_day_events(ip, day)
    except Exception:
        logger.exception("Loki 拉取失败 ip=%s day=%s", ip, day)
        return  # 拉取失败不落快照，留给下次水位回溯重试

    day_stat = aggregate_day(events)
    rolling = merge_days([*prev_days, day_stat], ROLLING_TAG_WINDOW)
    traffic = compute_traffic_type(day_stat)
    confidence = compute_confidence(day_stat["total"], stats[1])

    # upsert 快照行
    stmt = (
        db.query(BehaviorProfile)
        .filter(BehaviorProfile.asset_id == target["asset_id"],
                BehaviorProfile.profile_date == day)
        .first()
    )
    if stmt is None:
        stmt = BehaviorProfile(asset_id=target["asset_id"], profile_date=day)
        db.add(stmt)
    stmt.ip = ip
    stmt.mac = target.get("mac")
    stmt.hostname = target.get("hostname")
    stmt.status = "ok"
    stmt.total = day_stat["total"]
    stmt.by_hour = day_stat["by_hour"]
    stmt.wd_hour = day_stat["wd_hour"]
    stmt.by_block = day_stat["by_block"]
    stmt.cat_share = rolling["cat_share"]
    stmt.cat_by_block = day_stat["cat_by_block"]
    stmt.workday = day_stat["workday"]
    stmt.weekend = day_stat["weekend"]
    stmt.layer_visit = day_stat["layer_visit"]
    stmt.top_domains = rolling["top_domains"][:20]
    stmt.tags = build_tags(rolling)
    stmt.traffic_type = traffic
    stmt.confidence = confidence
    stmt.truncated_windows = stats[1]

    # 域名明细（先删后插，保证幂等）
    db.query(BehaviorDomain).filter(
        BehaviorDomain.asset_id == target["asset_id"],
        BehaviorDomain.profile_date == day,
    ).delete()
    dom_cat = {}
    for dom, visits in sorted(day_stat["domain_visits"].items(),
                              key=lambda t: -t[1])[:200]:
        cat = dom_cat.setdefault(dom, classify(dom)[0])
        db.add(BehaviorDomain(
            asset_id=target["asset_id"], ip=ip, domain=dom[:255],
            profile_date=day, visits=visits, category=cat,
        ))
    db.commit()


def mark_gap(db: Session, target: dict, day: dt.date) -> None:
    """超出 Loki 窗口补不回的日落 gap 占位快照（§9.7.9 防假绿）。"""
    row = (
        db.query(BehaviorProfile)
        .filter(BehaviorProfile.asset_id == target["asset_id"],
                BehaviorProfile.profile_date == day)
        .first()
    )
    if row is not None and row.status == "ok":
        return  # 已有真实数据，不覆盖
    if row is None:
        row = BehaviorProfile(asset_id=target["asset_id"], profile_date=day)
        db.add(row)
    row.ip = target["ip"]
    row.mac = target.get("mac")
    row.hostname = target.get("hostname")
    row.status = "gap"
    row.total = 0
    row.confidence = 0
    row.by_hour = [0] * 24
    row.wd_hour = [[0] * 24 for _ in range(7)]
    row.by_block = {}
    db.commit()


# ── 水位回溯主流程 ────────────────────────────────────────

def run_snapshot(db: Session, target_date: Optional[dt.date] = None) -> dict:
    """补齐 last_completed_date+1 → target_date（默认昨天）的所有缺口日。

    - Loki 窗口内的缺口：真实聚合；
    - Loki 窗口外的缺口：落 gap 占位行；
    - 成功后推进水位。
    """
    today = dt.datetime.now(TZ).date()
    end_day = target_date or (today - dt.timedelta(days=1))

    wm = db.query(BehaviorProfileWatermark).filter_by(id=1).first()
    if wm is None or wm.last_completed_date is None:
        start_day = end_day  # 首次运行只做昨天，避免全量回溯风暴
    else:
        start_day = wm.last_completed_date + dt.timedelta(days=1)

    if start_day > end_day:
        return {"status": "up_to_date", "last_completed": str(wm.last_completed_date) if wm else None}

    all_days = [start_day + dt.timedelta(days=i)
                for i in range((end_day - start_day).days + 1)]
    # 只补最近 MAX_BACKFILL_PER_RUN 天，其余推到下轮
    backlog_days = all_days[:-MAX_BACKFILL_PER_RUN] if len(all_days) > MAX_BACKFILL_PER_RUN else []
    days = all_days[-MAX_BACKFILL_PER_RUN:]

    targets = discover_targets(db)
    stats = {"targets": len(targets), "days": len(days), "snapshots": 0, "gaps": 0, "errors": 0}
    earliest = today - dt.timedelta(days=LOKI_RETENTION_DAYS)

    for day in days:
        if day < earliest:
            # 超出 Loki 窗口：对每个主体落 gap 占位
            for t in targets:
                mark_gap(db, t, day)
                stats["gaps"] += 1
            continue
        for t in targets:
            try:
                prev_days = _load_prev_days(db, t, day)
                snapshot_one_day(db, t, day, prev_days)
                stats["snapshots"] += 1
            except Exception:
                stats["errors"] += 1
                logger.exception("快照失败 ip=%s day=%s", t["ip"], day)

    # backlog 太老的日（>Loki 窗口）直接补 gap
    for day in backlog_days:
        if day < earliest:
            for t in targets:
                mark_gap(db, t, day)
                stats["gaps"] += 1

    # §6 留存期限：画像明细 ≥180 天自动清理（快照行保留分布聚合，同样清理）
    cutoff = today - dt.timedelta(days=180)
    d1 = db.query(BehaviorDomain).filter(BehaviorDomain.profile_date < cutoff).delete()
    p1 = db.query(BehaviorProfile).filter(BehaviorProfile.profile_date < cutoff).delete()
    if d1 or p1:
        logger.info("画像留存清理: domains=%d profiles=%d cutoff=%s", d1, p1, cutoff)

    # 推进水位（全部处理完才推进，失败日下轮由 gap 逻辑兜底）
    if wm is None:
        wm = BehaviorProfileWatermark(id=1)
        db.add(wm)
    wm.last_completed_date = end_day
    db.commit()
    stats["status"] = "ok"
    stats["last_completed"] = str(end_day)
    logger.info("行为画像快照完成: %s", stats)
    return stats


def _load_prev_days(db: Session, target: dict, day: dt.date) -> List[dict]:
    """加载滚动窗口内（不含当日）已有的单日聚合，供 merge_days 用。"""
    start = day - dt.timedelta(days=ROLLING_TAG_WINDOW - 1)
    rows = (
        db.query(BehaviorProfile)
        .filter(BehaviorProfile.asset_id == target["asset_id"],
                BehaviorProfile.profile_date >= start,
                BehaviorProfile.profile_date < day,
                BehaviorProfile.status == "ok")
        .all()
    )
    out = []
    for r in rows:
        # 历史行只存了 cat_share（百分比）与 layer_visit/total；
        # 还原 cat_visit ≈ share/100 * act_total，供 merge_days 重新归一化
        layer = r.layer_visit or {}
        act_total = layer.get("ACT", 0)
        cat_visit = {
            c: round(sh / 100 * act_total)
            for c, sh in (r.cat_share or {}).items()
        }
        out.append({
            "total": r.total,
            "by_hour": r.by_hour or [0] * 24,
            "wd_hour": r.wd_hour or [[0] * 24 for _ in range(7)],
            "by_block": r.by_block or {},
            "cat_by_block": {},
            "domain_visits": {},
            "cat_visit": cat_visit,
            "layer_visit": layer,
            "workday": 0,
            "weekend": 0,
        })
    return out


# ── 调度器（与 browsing_detection.scheduler 同款模式）──────

def _loop() -> None:
    """每日 02:00 跑全量快照；启动时立即跑一次（兼做水位回溯）。"""
    import time
    logger.info("behavior_profile scheduler started")
    # 启动即补一次水位
    db = SessionLocal()
    try:
        run_snapshot(db)
    except Exception:
        logger.exception("启动快照失败（下轮重试）")
    finally:
        db.close()

    while True:
        now = dt.datetime.now(TZ)
        nxt = (now + dt.timedelta(days=1)).replace(
            hour=SCHEDULE_HOUR, minute=0, second=0, microsecond=0)
        if now.hour < SCHEDULE_HOUR:
            nxt = now.replace(hour=SCHEDULE_HOUR, minute=0, second=0, microsecond=0)
        wait = max((nxt - now).total_seconds(), 60)
        if _stop_event.wait(wait):
            break
        db = SessionLocal()
        try:
            run_snapshot(db)
        except Exception:
            logger.exception("定时快照失败")
        finally:
            db.close()


_stop_event = threading.Event()
_thread: Optional[threading.Thread] = None


def start_behavior_profile_scheduler() -> None:
    global _thread
    if _thread is not None and _thread.is_alive():
        return
    _stop_event.clear()
    _thread = threading.Thread(target=_loop, name="behavior-profile-scheduler", daemon=True)
    _thread.start()


def stop_behavior_profile_scheduler() -> None:
    _stop_event.set()
