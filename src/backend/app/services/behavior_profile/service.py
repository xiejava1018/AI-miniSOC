"""画像查询服务（Phase 2）

读取快照表聚合输出，Loki 仅用于 realtime 下钻（当日/24h，§9.4 v1.5 口径）。
"""

import datetime as dt
import logging
from typing import List, Optional

from sqlalchemy import case as sa_case, func
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
    cat_by_block: dict = {}
    layer_visit: dict = {}
    workday = weekend = 0
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
        for b, cats in (getattr(r, "cat_by_block", None) or {}).items():
            cat_by_block.setdefault(b, {})
            for c, v in cats.items():
                cat_by_block[b][c] = cat_by_block[b].get(c, 0) + v
        workday += r.workday or 0
        weekend += r.weekend or 0
    if total:
        by_block = {b: round(v / total * 100, 1) for b, v in by_block.items()}
        layer_visit = {l: round(v / total * 100, 1) for l, v in layer_visit.items()}
    act_total = layer_visit.get("ACT", 0) or 1
    cat_by_block_pct = {
        b: {c: round(v / act_total * 100, 1) for c, v in sorted(cats.items(), key=lambda t: -t[1])[:6]}
        for b, cats in cat_by_block.items() if cats
    }

    tags = latest.tags if latest else []
    domains = get_domains(db, ip, days, limit=20)

    return {
        "ip": ip,
        "asset": {
            "id": str(asset.id) if asset else None,
            "name": asset.name if asset else (latest.hostname if latest else None),
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
        "workday": workday,
        "weekend": weekend,
        "cat_by_block": cat_by_block_pct,
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


# ── 风险画像（层3，对标原型 §3.0.2） ─────────────────────

def get_risk(db: Session, ip: str) -> dict:
    """风险画像：告警分级/规则榜/漏洞/暴露端口/评分趋势（复用现有权威实现）。"""
    from app.core.alert_levels import LEVEL_CRITICAL, LEVEL_HIGH
    from app.models.asset_port import AssetPort
    from app.models.asset_risk import AssetRiskHistory
    from app.models.vulnerability import AssetVulnerability, Vulnerability
    from app.services.alert_query import AlertQueryService

    asset = db.query(Asset).filter(Asset.asset_ip == ip).first()
    # 告警分级：服务端聚合精确计数（禁客户端分桶，§F2.1 教训）
    try:
        buckets = AlertQueryService(db).get_level_buckets_by_ip(ip, days=7)
    except Exception:
        logger.exception("告警分级聚合失败 ip=%s", ip)
        buckets = {"critical": 0, "high": 0, "medium": 0, "low": 0,
                   "total": 0, "exact": False}

    # 告警规则榜（PG 聚合表，按 count 排序；附 AI 去噪后计数）
    from app.models.alert_group_snapshot import AlertGroupSnapshot as AlertGroup
    rules = (
        db.query(
            AlertGroup.rule_id, AlertGroup.rule_description,
            AlertGroup.level_max.label("level"), func.sum(AlertGroup.count).label("cnt"),
            func.sum(func.coalesce(
                sa_case((AlertGroup.ai_is_noise == False, AlertGroup.count),  # noqa: E712
                        else_=0), 0)).label("real_cnt"),
        )
        .filter(AlertGroup.agent_ip == ip)
        .group_by(AlertGroup.rule_id, AlertGroup.rule_description, AlertGroup.level_max)
        .order_by(func.sum(AlertGroup.count).desc())
        .limit(8)
        .all()
    )

    # 漏洞（open 状态，含 KEV/在野利用标）
    vuln_rows = (
        db.query(Vulnerability, AssetVulnerability.status)
        .join(AssetVulnerability, AssetVulnerability.vulnerability_id == Vulnerability.id)
        .filter(AssetVulnerability.asset_id == asset.id,
                AssetVulnerability.status != "fixed")
        .all() if asset else []
    )
    sev_dist = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    kev = []
    for v, _status in vuln_rows:
        sev = str(v.severity).lower()
        if sev in sev_dist:
            sev_dist[sev] += 1
        if v.has_exploit and len(kev) < 10:
            kev.append({"cve_id": v.cve_id, "title": v.title,
                        "severity": str(v.severity)})

    # 暴露端口
    ports = (
        db.query(AssetPort)
        .filter(AssetPort.asset_ip == ip, AssetPort.state == "open")
        .order_by(AssetPort.port)
        .all()
    )
    danger_ports = {22, 3389, 5900, 5901, 23, 445, 135, 6379, 27017}
    port_items = [
        {"port": p.port, "protocol": p.protocol, "service": p.service,
         "danger": int(p.port) in danger_ports}
        for p in ports
    ]

    # 评分趋势（快照可能只有几天——诚实返回天数）
    trend = []
    if asset:
        hist = (
            db.query(AssetRiskHistory)
            .filter(AssetRiskHistory.asset_id == asset.id)
            .order_by(AssetRiskHistory.scored_at.desc())
            .limit(30)
            .all()
        )
        trend = [{"date": h.scored_at.date().isoformat(), "score": h.risk_score}
                 for h in reversed(hist)]

    has_agent_alerts = buckets.get("total", 0) > 0 or bool(rules)
    return {
        "ip": ip,
        "asset_id": str(asset.id) if asset else None,
        "criticality": asset.criticality if asset else None,
        "alerts": buckets,
        "top_rules": [
            {"rule_id": r[0], "description": r[1], "level": r[2], "count": int(r[3]),
             "real_count": int(r[4] or 0)}
            for r in rules
        ],
        "vulns": {"total": sum(sev_dist.values()), "severity": sev_dist, "kev": kev},
        "ports": {"total": len(port_items), "items": port_items},
        "risk_trend": trend,
        "risk_trend_days": len(trend),
        "note": None if has_agent_alerts or ports else "该设备无主机侧告警与端口数据（未装 agent 且未扫描）",
    }


# ── 异常判定（层5，可计算子集；解读者须人工复核） ─────────

def get_anomalies(db: Session, ip: str) -> dict:
    """画像异常信号（只输出信号不定性）。与推送场景 8 同口径。"""
    rows = [r for r in find_by_ip(db, ip, days=30)]
    ok_rows = [r for r in rows if r.status == "ok"]
    gap_days = sum(1 for r in rows if r.status == "gap")
    signals = []

    def add(sev, name, desc, evidence):
        signals.append({"severity": sev, "name": name, "desc": desc, "evidence": evidence})

    if len(ok_rows) >= 4:
        latest, baseline = ok_rows[-1], ok_rows[:-1]
        base_total = [r.total for r in baseline if r.total > 0]
        if base_total and latest.total >= 500:
            avg = sum(base_total) / len(base_total)
            if avg > 0 and latest.total / avg >= 5:
                add("mid", "访问量激增",
                    "最近快照日访问量显著高于历史基线",
                    f"{latest.total:,} 次 vs 基线均值 {avg:,.0f} 次"
                    f"（{latest.total / avg:.1f} 倍，阈值 5 倍）")
        if base_total:
            night_now = _night_share(latest.by_hour)
            base_nights = [_night_share(r.by_hour) for r in baseline if r.total > 0]
            base_night_avg = sum(base_nights) / len(base_nights) if base_nights else 0
            if night_now >= 40 and base_night_avg < 20:
                add("mid", "节律突变（凌晨活跃）",
                    "凌晨 00-06 点占比显著高于自身基线",
                    f"最新 {night_now}% vs 基线均值 {base_night_avg:.0f}%")
        if latest.traffic_type == "machine":
            add("info", "机器流量为主",
                "系统/协议心跳占比高，作息与兴趣结论不适用",
                f"SYS 层占比 {latest.layer_visit.get('SYS', 0)}%")
        if getattr(latest, "truncated_windows", 0) > 0:
            add("info", "数据截断",
                "当日部分查询窗口被截断，计数可能偏低",
                f"truncated_windows={latest.truncated_windows}")
    if gap_days:
        add("info", "数据缺失",
            "部分快照日超出 Loki 保留窗口，永久缺失",
            f"{gap_days} 天 gap（非 0 流量，勿当作无行为）")
    if (ok_rows[-1].confidence if ok_rows else 0) < 40 and ok_rows:
        add("info", "低置信度",
            "数据量不足，画像结论可信度有限",
            f"confidence={ok_rows[-1].confidence}/100")

    hit = [s for s in signals if s["severity"] in ("high", "mid")]
    return {
        "ip": ip,
        "signals": signals,
        "has_anomaly": bool(hit),
        "banner": {
            "severity": hit[0]["severity"],
            "name": hit[0]["name"],
            "desc": hit[0]["desc"],
        } if hit else None,
        "disclaimer": "画像仅输出信号，不定性；定性须经人工复核",
    }


def get_domain_daily(db: Session, ip: str, domain: str, days: int = 30) -> list:
    """单域名逐日访问明细（域名下钻）。"""
    since = dt.date.today() - dt.timedelta(days=days)
    rows = (
        db.query(BehaviorDomain)
        .filter(BehaviorDomain.ip == ip, BehaviorDomain.domain == domain,
                BehaviorDomain.profile_date >= since)
        .order_by(BehaviorDomain.profile_date)
        .all()
    )
    return [{"date": str(r.profile_date), "visits": r.visits,
             "category": r.category} for r in rows]


def compare_profiles(db: Session, ip_a: str, ip_b: str, days: int = 7) -> dict:
    """双 IP 画像对比（余弦相似度：by_block + cat_share）。"""
    pa, pb = get_profile(db, ip_a, days), get_profile(db, ip_b, days)
    if not pa or not pb:
        missing = ip_a if not pa else ip_b
        return {"error": f"{missing} 无画像快照"}

    import math

    def cos(a: dict, b: dict) -> float:
        keys = set(a) | set(b)
        num = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
        na = math.sqrt(sum(v * v for v in a.values())) or 1
        nb = math.sqrt(sum(v * v for v in b.values())) or 1
        return round(num / (na * nb), 3)

    block_sim = cos(pa["by_block"], pb["by_block"])
    cat_sim = cos(pa["cat_share"], pb["cat_share"])
    return {
        "a": {"ip": ip_a, "total": pa["total"], "traffic_type": pa["traffic_type"],
              "night": pa["by_block"].get("深夜", 0)},
        "b": {"ip": ip_b, "total": pb["total"], "traffic_type": pb["traffic_type"],
              "night": pb["by_block"].get("深夜", 0)},
        "days": days,
        "block_similarity": block_sim,
        "category_similarity": cat_sim,
        "verdict": (
            "行为模式高度相似" if block_sim > 0.9 and cat_sim > 0.9
            else "行为模式部分相似" if block_sim > 0.7
            else "行为模式差异明显"
        ),
        "note": "相似度为粗粒度参考，判定需人工复核",
    }
