"""行为维 UEBA 引擎（OH-2.8 · 八维⑧ / S8 僵尸资产前置）

两个能力：

  1. ``score_behavior_anomaly(row, asset_type)``：单资产行为异常评分（纯函数，
     消费 BehaviorProfile 日快照，无额外查询）——夜间占比 / 周末占比 /
     流量类型错配 / 风险标签，输出 0-100 分 + 信号明细。
     数据缺失（status=gap / 字段空）取中性，不罚分（假绿防护的反面：
     缺数据不是异常证据）。
  2. ``detect_zombies(db, days)``：僵尸资产候选——台账在册但近 N 天
     ① 无行为画像快照（或总量为 0）且 ② 无认证类身份事件。
     输出候选 + 证据 + 置信度（仅候选，人工确认后处理；S8 闭环入口）。

边界：UEBA 是启发式评分不是定论；所有结论都带信号明细供人工复核。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.behavior_profile import BehaviorProfile
from app.models.identity import IdentityEvent

logger = logging.getLogger(__name__)

# ── 异常评分阈值（v1 启发式，后续 OH-7.3 权重学习校准） ──
NIGHT_HOURS = range(0, 7)          # 00:00-06:59
NIGHT_RATIO_HIGH = 0.30            # 夜间流量占比 ≥30% → 信号
WEEKEND_RATIO_HIGH = 0.40          # 周末占比 ≥40% → 信号
MACHINE_TYPES = {"server", "network_device", "cloud"}
HUMAN_TYPES = {"workstation", "iot"}

# 标签关键词 → 风险标签（tagger 输出的中文名，按需增补）
_RISKY_TAG_KEYWORDS = ("夜猫", "夜间", "加密", "挖矿", "代理", "翻墙", "异常", "风险")


def score_behavior_anomaly(
    row: Optional[BehaviorProfile],
    asset_type: Optional[str] = None,
) -> Dict[str, Any]:
    """单资产行为异常评分（纯函数）。

    row 为 None（无快照）→ 中性结果 score=None（无数据不判异常）。
    """
    if row is None:
        return {
            "anomaly_score": None,
            "signals": [],
            "basis": "no_snapshot",
            "profile_date": None,
        }

    signals: List[Dict[str, Any]] = []
    score = 0

    # 数据缺失保护：gap 日不参与异常判定
    if row.status == "gap":
        return {
            "anomaly_score": None,
            "signals": [],
            "basis": "data_gap",
            "profile_date": str(row.profile_date) if row.profile_date else None,
        }

    total = row.total or 0
    if total == 0:
        # 当日零流量：本身不异常（可能是合法静默），交给僵尸检测判断
        return {
            "anomaly_score": 0,
            "signals": [],
            "basis": "zero_traffic",
            "profile_date": str(row.profile_date) if row.profile_date else None,
        }

    # ① 夜间占比（by_hour 24 数组）
    night_visits = 0
    by_hour = row.by_hour or []
    if isinstance(by_hour, list) and len(by_hour) == 24:
        night_visits = sum(int(v or 0) for v in by_hour[:7])
        night_ratio = night_visits / max(total, 1)
        if night_ratio >= NIGHT_RATIO_HIGH:
            score += 30
            signals.append({
                "kind": "night_activity",
                "detail": f"夜间(00-07)流量占比 {night_ratio:.0%}",
                "weight": 30,
            })

    # ② 周末占比
    weekend = row.weekend or 0
    if total > 0:
        weekend_ratio = weekend / total
        if weekend_ratio >= WEEKEND_RATIO_HIGH:
            score += 20
            signals.append({
                "kind": "weekend_activity",
                "detail": f"周末流量占比 {weekend_ratio:.0%}",
                "weight": 20,
            })

    # ③ 流量类型与资产类型错配
    tt = row.traffic_type
    if asset_type and tt:
        mismatch = (
            (tt == "human" and asset_type in MACHINE_TYPES)
            or (tt == "machine" and asset_type in HUMAN_TYPES)
        )
        if mismatch:
            score += 25
            signals.append({
                "kind": "traffic_type_mismatch",
                "detail": f"资产类型 {asset_type} 但流量类型 {tt}",
                "weight": 25,
            })

    # ④ 风险标签
    risky_tags: List[str] = []
    if row.tags and isinstance(row.tags, list):
        for t in row.tags:
            name = t.get("name", "") if isinstance(t, dict) else str(t)
            if any(k in name for k in _RISKY_TAG_KEYWORDS):
                risky_tags.append(name)
    if risky_tags:
        score += min(25, 15 * len(risky_tags))
        signals.append({
            "kind": "risky_tags",
            "detail": f"风险标签：{'、'.join(risky_tags[:5])}",
            "weight": min(25, 15 * len(risky_tags)),
        })

    return {
        "anomaly_score": min(score, 100),
        "signals": signals,
        "basis": "behavior_snapshot",
        "profile_date": str(row.profile_date) if row.profile_date else None,
        "traffic_type": tt,
        "total_visits": total,
    }


def detect_zombies(
    db: Session,
    *,
    days: int = 14,
) -> Dict[str, Any]:
    """僵尸资产候选：在册资产近 N 天无行为流量且无认证事件。

    返回候选列表（含证据），非终局结论——须人工确认。
    """
    cutoff = datetime.utcnow() - timedelta(days=days)

    # 各资产近 N 天行为流量合计 + 最近快照
    beh_rows = (
        db.query(
            BehaviorProfile.asset_id,
            sa_func.sum(BehaviorProfile.total).label("visits"),
            sa_func.max(BehaviorProfile.profile_date).label("last_date"),
        )
        .filter(
            BehaviorProfile.asset_id.isnot(None),
            BehaviorProfile.profile_date >= cutoff.date(),
        )
        .group_by(BehaviorProfile.asset_id)
        .all()
    )
    beh_by_asset = {str(r.asset_id): (int(r.visits or 0), str(r.last_date))
                    for r in beh_rows}

    # 各资产近 N 天认证事件数（按 dst_ip 锚资产 IP）
    idn_rows = (
        db.query(IdentityEvent.dst_ip, sa_func.count(IdentityEvent.id))
        .filter(IdentityEvent.ts >= cutoff, IdentityEvent.dst_ip.isnot(None))
        .group_by(IdentityEvent.dst_ip)
        .all()
    )
    idn_by_ip = {str(r[0]): int(r[1]) for r in idn_rows}

    assets = db.query(Asset).all()
    candidates: List[Dict[str, Any]] = []
    checked = 0
    for a in assets:
        if a.id is None:
            continue
        checked += 1
        aid = str(a.id)
        visits, last_date = beh_by_asset.get(aid, (0, None))
        auth_events = idn_by_ip.get(str(a.asset_ip or ""), 0)

        if visits > 0 or auth_events > 0:
            continue  # 有活动，不是僵尸

        # 置信度：快照体系覆盖到该资产但零流量 → 更可信的僵尸
        has_snapshot_history = (
            db.query(sa_func.count(BehaviorProfile.id))
            .filter(BehaviorProfile.asset_id == a.id)
            .scalar() or 0
        ) > 0
        confidence = 0.7 if has_snapshot_history else 0.4

        candidates.append({
            "asset_id": aid,
            "name": a.name,
            "asset_ip": str(a.asset_ip) if a.asset_ip else None,
            "asset_type": a.asset_type,
            "evidence": {
                "behavior_visits_window": visits,
                "last_profile_date": last_date,
                "identity_events_window": auth_events,
                "window_days": days,
                "has_snapshot_history": has_snapshot_history,
            },
            "confidence": confidence,
        })

    candidates.sort(key=lambda c: -c["confidence"])
    logger.info("OH-2.8 僵尸候选：%d/%d（窗口 %d 天）", len(candidates), checked, days)
    return {
        "window_days": days,
        "checked": checked,
        "zombie_count": len(candidates),
        "candidates": candidates,
        "note": "候选须人工确认；置信 0.7=有画像史但窗口内零流量，0.4=无画像史",
    }


def zombie_clearance_rate(db: Session) -> Dict[str, Any]:
    """S8 僵尸清零率（OH-4.8 验收口径）。

    分母 = 曾被检出僵尸并派单的资产数（ueba_zombie 工单，按 asset 去重）
    分子 = 其中已 verified（真正清零）的资产数。cancelled 单独列出（不
    计入清零——误报/撤销不等同处置清零）。

    这是闭环度量，纯读不写。
    """
    from app.models.remediation_ticket import (
        RemediationTicket, SOURCE_UEBA_ZOMBIE,
        STATUS_VERIFIED, STATUS_CANCELLED,
    )
    rows = (
        db.query(
            RemediationTicket.asset_id,
            RemediationTicket.status,
        )
        .filter(
            RemediationTicket.source_type == SOURCE_UEBA_ZOMBIE,
            RemediationTicket.asset_id.isnot(None),
        )
        .all()
    )
    # 每个资产取其最“终局”的状态
    best: Dict[str, str] = {}
    rank = {"verified": 3, "cancelled": 2, "resolved": 1,
            "in_progress": 1, "reopened": 0, "open": 0}
    for asset_id, status in rows:
        key = str(asset_id)
        if key not in best or rank.get(status, 0) > rank.get(best[key], 0):
            best[key] = status

    total = len(best)
    cleared = sum(1 for s in best.values() if s == STATUS_VERIFIED)
    cancelled = sum(1 for s in best.values() if s == STATUS_CANCELLED)
    return {
        "dispatched_assets": total,
        "cleared_assets": cleared,
        "cancelled_assets": cancelled,
        "in_flight_assets": total - cleared - cancelled,
        "clearance_rate": round(cleared / total, 4) if total else None,
        "note": "清零率=verified 资产/派单资产；cancelled 不计清零（误报撤销）",
    }
