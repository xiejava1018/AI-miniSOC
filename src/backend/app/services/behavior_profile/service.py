"""画像查询服务（Phase 2）

读取快照表聚合输出，Loki 仅用于 realtime 下钻（当日/24h，§9.4 v1.5 口径）。
"""

import datetime as dt
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.behavior_profile import BehaviorDomain, BehaviorProfile
from .aggregator import aggregate_day, compute_traffic_type, merge_days
from .loki_source import TZ
from .loki_source import fetch_day_events
from .tagger import build_tags, compute_confidence

# 展示字段白名单（快照行 → dict）
_PROFILE_FIELDS = (
    "ip", "mac", "hostname", "profile_date", "status", "total",
    "by_hour", "wd_hour", "by_block", "cat_share", "layer_visit",
    "top_domains", "tags", "traffic_type", "confidence", "truncated_windows",
    "generated_at",
)


def _serialize(row: BehaviorProfile) -> dict:
    out = {k: getattr(row, k) for k in _PROFILE_FIELDS}
    if out.get("profile_date") is not None:
        out["profile_date"] = str(out["profile_date"])
    if out.get("generated_at") is not None:
        out["generated_at"] = out["generated_at"].isoformat()
    out["asset_id"] = str(row.asset_id) if row.asset_id else None
    return out


def find_by_ip(db: Session, ip: str, days: int = 7) -> List[BehaviorProfile]:
    """按 IP 取最近 N 天快照（含未纳管主体；IP 漂移的主体按 ip 索引）"""
    since = dt.date.today() - dt.timedelta(days=days)
    return (
        db.query(BehaviorProfile)
        .filter(BehaviorProfile.ip == ip, BehaviorProfile.profile_date >= since)
        .order_by(BehaviorProfile.profile_date.desc())
        .all()
    )


def get_profile(db: Session, ip: str, days: int = 7) -> Optional[dict]:
    """聚合画像：最近 N 天快照合并 + 实体信息。无任何快照返回 None。"""
    rows = find_by_ip(db, ip, days)
    latest = rows[0] if rows else None
    asset = db.query(Asset).filter(Asset.asset_ip == ip).first()

    ok_rows = [r for r in rows if r.status == "ok"]
    gap_count = sum(1 for r in rows if r.status == "gap")
    if not ok_rows and not rows:
        return None

    # 多日合并：单日 by_hour/wd_hour 相加，分布重算
    total = sum(r.total for r in ok_rows)
    by_hour = [0] * 24
    wd_hour = [[0] * 24 for _ in range(7)]
    by_block: dict = {}
    layer_visit: dict = {}
    for r in ok_rows:
        for h in range(24):
            by_hour[h] += (r.by_hour or [0] * 24)[h]
        for i in range(7):
            for h in range(24):
                wd_hour[i][h] += (r.wd_hour or [[0] * 24 for _ in range(7)])[i][h]
        for b, v in (r.by_block or {}).items():
            by_block[b] = by_block.get(b, 0) + v
        for l, v in (r.layer_visit or {}).items():
            layer_visit[l] = layer_visit.get(l, 0) + v
    if total:
        by_block = {b: round(v / total * 100, 1) for b, v in by_block.items()}
        layer_visit = {l: round(v / total * 100, 1) for l, v in layer_visit.items()}

    tags = latest.tags if latest else []
    domains = get_domains(db, ip, days, limit=20)

    return {
        "ip": ip,
        "asset": {
            "id": str(asset.id) if asset else None,
            "name": asset.asset_name if asset else (latest.hostname if latest else None),
            "asset_type": asset.asset_type if asset else None,
            "os_name": asset.os_name if asset else None,
            "owner": asset.owner if asset else None,
            "mac_address": asset.mac_address if asset else None,
            "criticality": asset.criticality if asset else None,
        } if asset else None,
        "days": days,
        "total": total,
        "gap_days": gap_count,
        "by_hour": by_hour,
        "wd_hour": wd_hour,
        "by_block": by_block,
        "layer_visit": layer_visit,
        "cat_share": latest.cat_share if latest else {},
        "top_domains": domains,
        "tags": tags,
        "traffic_type": latest.traffic_type if latest else "human",
        "confidence": latest.confidence if latest else 0,
        "daily": [_serialize(r) for r in rows],
    }


def get_profiles_summary(db: Session, traffic_type: Optional[str] = None,
                         limit: int = 100) -> List[dict]:
    """全部主体画像摘要（列表页）：取每主体最近一个非 gap 快照。"""
    q = (
        db.query(BehaviorProfile)
        .filter(BehaviorProfile.status == "ok")
    )
    if traffic_type:
        q = q.filter(BehaviorProfile.traffic_type == traffic_type)
    latest_ids = [
        row[1] for row in db.query(
            BehaviorProfile.ip,
            func.max(BehaviorProfile.id),
        ).filter(BehaviorProfile.status == "ok").group_by(BehaviorProfile.ip).all()
    ]
    q = q.filter(BehaviorProfile.id.in_(latest_ids))
    rows = q.order_by(BehaviorProfile.total.desc()).limit(limit).all()
    return [
        {
            "ip": r.ip,
            "asset_id": str(r.asset_id) if r.asset_id else None,
            "hostname": r.hostname,
            "profile_date": str(r.profile_date),
            "total": r.total,
            "traffic_type": r.traffic_type,
            "confidence": r.confidence,
            "tags": (r.tags or [])[:3],
            "night_share": _night_share(r.by_hour),
        }
        for r in rows
    ]


def _night_share(by_hour) -> float:
    if not by_hour or not sum(by_hour):
        return 0.0
    return round(sum(by_hour[:6]) / sum(by_hour) * 100, 1)


def get_domains(db: Session, ip: str, days: int = 7, limit: int = 50,
                category: Optional[str] = None) -> List[dict]:
    """域名 TOP N（跨天聚合，来自 soc_behavior_domains）。"""
    since = dt.date.today() - dt.timedelta(days=days)
    q = (
        db.query(
            BehaviorDomain.domain,
            func.sum(BehaviorDomain.visits).label("visits"),
        )
        .filter(BehaviorDomain.ip == ip, BehaviorDomain.profile_date >= since)
        .group_by(BehaviorDomain.domain)
        .order_by(func.sum(BehaviorDomain.visits).desc())
        .limit(limit)
    )
    if category:
        q = q.having(func.bool_or(BehaviorDomain.category == category))
    rows = q.all()
    total = sum(v for _, v in rows) or 1
    from .classifier import classify
    return [
        {"domain": d, "visits": int(v),
         "category": classify(d)[0], "share": round(v / total * 100, 2)}
        for d, v in rows
    ]


def get_trend(db: Session, ip: str, days: int = 30) -> List[dict]:
    """多日趋势（快照表直接按日返回，gap 日显式标记）。"""
    rows = find_by_ip(db, ip, days)
    return [
        {
            "profile_date": str(r.profile_date),
            "status": r.status,
            "total": r.total,
            "traffic_type": r.traffic_type,
            "confidence": r.confidence,
            "night_share": _night_share(r.by_hour),
            "act_ratio": _act_ratio(r.layer_visit),
        }
        for r in reversed(rows)
    ]


def _act_ratio(layer_visit) -> float:
    if not layer_visit:
        return 0.0
    total = sum(layer_visit.values()) or 1
    return round(layer_visit.get("ACT", 0) / total * 100, 1)


def compute_realtime(db: Session, ip: str) -> dict:
    """当日/24h 实时画像（§9.4：realtime 仅限当日口径，避免 7 天拉取超时）。"""
    today = dt.datetime.now(TZ).date()
    events, stats = fetch_day_events(ip, today)
    day_stat = aggregate_day(events)
    rolling = merge_days([day_stat], 1)
    return {
        "ip": ip,
        "date": str(today),
        "total": day_stat["total"],
        "by_hour": day_stat["by_hour"],
        "wd_hour": day_stat["wd_hour"],
        "by_block": day_stat["by_block"],
        "layer_visit": day_stat["layer_visit"],
        "traffic_type": compute_traffic_type(day_stat),
        "confidence": compute_confidence(day_stat["total"], stats[1]),
        "tags": build_tags(rolling),
        "loki_requests": stats[0],
        "truncated_windows": stats[1],
    }
