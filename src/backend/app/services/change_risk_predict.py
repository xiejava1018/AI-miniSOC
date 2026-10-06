"""变更风险预测（OH-4.10 · S11）

在 F3.1 变更影响分析（impact_analysis.py，回答「会影响谁」）之上，
S11 回答下一层问题：**这次变更有多大概率出事、出了会有多大、窗口内有哪些
历史征兆**。复用既有能力，不重写：

  - 目标定位/关键词     → ``impact_analysis._extract_keywords`` / ``_locate_assets``
  - 关联拓扑            → ``impact_analysis._related_assets``
  - 跨三源历史事件       → ``federation.timeline_service.TimelineService``
    （底座 P0 已就绪——这是 S11 从「粗粒度降级」升级的关键前置）
  - 告警分级权威         → ``alert_levels`` / AlertQueryService（不裸数 severity）

预测分（0-100，越高越危险）= 纯函数合成，**不调用 LLM**：
  历史高危事件密度 + 窗口内告警征兆 + 资产重要性 + 影响面广度，
每一项都带 contributing_factors，可复算可对质。AI 解读在展示层另做，
无法反向影响判定（与 compliance.py 同红线）。

边界（诚实披露）：
  - 这是**基于历史频次的启发式预测**，不是变更成功概率模型（无变更结果
    标注语料）；输出措辞统一用「风险」而非「成功率」。
  - Loki 不可达时 TimelineService 自动降级（source_status=error），
    本预测据可用源计算并在 degraded_sources 中列明，不伪造覆盖。
  - 拓扑为计算兜底（edge_source=computed_fallback）时影响面广度降权。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.core.alert_levels import LEVEL_HIGH
from app.services import impact_analysis as ia
from app.services.federation.schemas import AssetAnchor, EventType
from app.services.federation.timeline_service import TimelineService

logger = logging.getLogger(__name__)

# 历史回溯窗口（天）：用过去这段的事件密度预测变更风险
HISTORY_WINDOW_DAYS = 14

# 分值权重（合起来封顶 100）
W_HISTORY = 40      # 历史高危事件密度
W_ALERT_SIGNS = 25  # 窗口内已有高危告警征兆
W_IMPORTANCE = 20   # 目标资产重要性
W_BLAST = 15        # 影响面广度


class ChangeRiskPredictor:
    """变更风险预测器（每请求一个实例）。"""

    def __init__(self, db: Session):
        self.db = db
        self.timeline = TimelineService(db)

    async def predict(
        self,
        change_description: str,
        change_window_hours: int = 4,
        history_days: int = HISTORY_WINDOW_DAYS,
    ) -> Dict[str, Any]:
        if not change_description or len(change_description.strip()) < 3:
            raise ValueError("change_description 太短（至少 3 字符）")
        if not (1 <= change_window_hours <= 168):
            raise ValueError("change_window_hours 须在 1-168")
        if not (1 <= history_days <= 90):
            raise ValueError("history_days 须在 1-90")

        keywords = ia._extract_keywords(change_description)
        targets = ia._locate_assets(self.db, keywords)

        if not targets:
            return {
                "risk_score": None,
                "risk_level": "unknown",
                "identified": False,
                "change_description": change_description,
                "message": "未识别到具体资产，无法预测——请补充 IP/主机名",
                "contributing_factors": [],
                "degraded_sources": [],
            }

        now = datetime.now(timezone.utc)
        start = now - timedelta(days=history_days)

        per_target: List[Dict[str, Any]] = []
        all_degraded: set[str] = set()
        for t in targets:
            tl = await self.timeline.get_timeline(
                AssetAnchor.from_asset(t),
                start.replace(tzinfo=None),
                now.replace(tzinfo=None),
                types=[EventType.ALERT, EventType.CHANGE, EventType.VULN],
                limit=200,
            )
            for src, st in tl.source_status.items():
                if st in ("error", "timeout"):
                    all_degraded.add(src)

            rel = ia._related_assets(self.db, t)
            per_target.append({
                "asset": ia._serialize_asset(t),
                "events": tl.events,
                "coverage_note": tl.coverage_note,
                "related_count": (
                    len(rel["same_segment"]) + len(rel["shared_tags"])
                ),
                "edge_source": rel.get("edge_source", "computed_fallback"),
            })

        score, factors = self._score(per_target, history_days)
        return {
            "risk_score": score,
            "risk_level": self._level(score),
            "identified": True,
            "change_description": change_description,
            "change_window_hours": change_window_hours,
            "history_days": history_days,
            "targets": [p["asset"] for p in per_target],
            "contributing_factors": factors,
            "degraded_sources": sorted(all_degraded),
            "evidence_summary": self._evidence_summary(per_target),
            "red_line": "启发式历史风险预测，非成功率模型；不伪造源覆盖",
        }

    # ---------------- internals ----------------

    def _score(self, per_target: List[Dict[str, Any]], days: int):
        factors: List[str] = []
        score = 0

        # 1) 历史高危事件密度
        high_events = 0
        total_events = 0
        for p in per_target:
            for e in p["events"]:
                total_events += 1
                if (e.severity or 0) >= LEVEL_HIGH:
                    high_events += 1
        # 每目标每天 ≥0.3 个高危事件即拉满该项（14 天 ≈ 4+ 事件）
        n = len(per_target)
        density = high_events / max(n * days * 0.3, 1e-9)
        h = min(W_HISTORY, round(W_HISTORY * min(density, 1.0)))
        score += h
        if high_events:
            factors.append(
                f"近 {days} 天高危事件 {high_events} 个（+{h}）"
            )

        # 2) 窗口内告警征兆：最近 24h 是否已有高危
        recent_cut = datetime.utcnow() - timedelta(days=1)
        recent_high = 0
        for p in per_target:
            recent_high += sum(
                1 for e in p["events"]
                if e.ts >= recent_cut and (e.severity or 0) >= LEVEL_HIGH
            )
        if recent_high:
            a = min(W_ALERT_SIGNS, recent_high * 10)
            score += a
            factors.append(f"近 24h 已有高危告警 {recent_high} 个（+{a}）")

        # 3) 资产重要性（取目标最高）
        imp_rank = {"core": 4, "important": 3, "normal": 2, "auxiliary": 1}
        top_imp = max(
            (imp_rank.get(p["asset"].get("business_impact", "normal"), 2)
             for p in per_target),
            default=2,
        )
        i = round(W_IMPORTANCE * top_imp / 4)
        score += i
        if top_imp >= 3:
            factors.append(f"目标业务重要度 rank={top_imp}（+{i}）")

        # 4) 影响面广度（平均关联数，计算兜底降权）
        if per_target:
            avg_rel = sum(p["related_count"] for p in per_target) / len(per_target)
            trusted = all(p["edge_source"] != "computed_fallback" for p in per_target)
            blast_raw = min(avg_rel / 8.0, 1.0)
            if not trusted:
                blast_raw *= 0.5  # 兜底拓扑不放大
            b = round(W_BLAST * blast_raw)
            score += b
            if avg_rel >= 3:
                factors.append(
                    f"平均关联资产 {avg_rel:.0f}（+{b}"
                    + ("，兜底拓扑半权）" if not trusted else "）")
                )

        return max(0, min(100, score)), factors

    @staticmethod
    def _level(score: int) -> str:
        if score >= 60:
            return "high"
        if score >= 30:
            return "medium"
        return "low"

    def _evidence_summary(self, per_target: List[Dict[str, Any]]):
        return [
            {
                "asset": p["asset"].get("name"),
                "event_count": len(p["events"]),
                "coverage_note": p["coverage_note"],
                "related_count": p["related_count"],
                "edge_source": p["edge_source"],
            }
            for p in per_target
        ]
