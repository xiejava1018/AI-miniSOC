"""
告警摘要服务

组合 AlertQueryService 的聚合能力，产出一份可查询、可推送的"告警治理摘要"。
Phase0：summary_text 由模板生成（不调 AI，先让"看得见"）；Phase1 起接入 AI 簇级研判。
建表复用 browsing 范式：Base.metadata.create_all(checkfirst，幂等)，不依赖 Alembic。
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from app.core.database import engine
from app.models.base import Base
import app.models  # noqa: F401  确保模型注册
from app.models import AlertDigest, AlertGroupAnalysis
from app.services.alert_query import AlertQueryService
from app.services.alert_group_triage_service import AlertGroupTriageService
from app.services.alert_governance_config import get_triage_top_n

logger = logging.getLogger(__name__)


class AlertDigestService:
    """告警摘要编排服务"""

    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _ensure_tables() -> None:
        Base.metadata.create_all(
            bind=engine, tables=[AlertDigest.__table__, AlertGroupAnalysis.__table__], checkfirst=True
        )

    # ── 生成 ─────────────────────────────────────────

    async def generate(self, hours: int = 24) -> AlertDigest:
        """生成一份摘要并落库，返回模型实例。

        Phase 1：TopN 告警簇接入 AI 研判（triage_top_groups），把 verdict 写回
        top_groups 的 ai_* 字段，summary_text 改为"今日必处理"综述，ai_model 写实模型名。
        AI 不可用时降级为纯聚合 + 启发式 verdict（source='heuristic'）。
        """
        self._ensure_tables()
        svc = AlertQueryService(self.db)
        end = datetime.utcnow()
        start = end - timedelta(hours=hours)

        top_n = get_triage_top_n(self.db)

        # 1. 告警簇（TopN）+ AI 研判（并发，失败降级）
        try:
            triage_svc = AlertGroupTriageService(self.db)
            groups = await triage_svc.triage_top_groups(hours=hours, top_n=top_n)
        except Exception as e:
            logger.warning("AI 研判失败，降级为纯聚合: %s", e)
            groups = svc.get_alert_groups(hours=hours, min_count=1, limit=top_n).get("groups", [])

        # 2. 高频资产 + 资产关联
        top_assets = svc.get_top_alert_assets(hours=hours, limit=10)
        top_assets = self._enrich_assets(top_assets)

        # 3. 趋势
        interval = max(1, hours // 24) if hours >= 24 else max(1, hours // 6)
        trend = svc.get_alert_trend(hours=hours, interval_hours=interval)

        # 4. 等级分布
        stats = svc.get_alert_statistics(start_time=start, end_time=end)

        # 5. 原始告警总数
        total = 0
        try:
            total = svc.get_alerts(offset=0, limit=1, start_time=start, end_time=end).get("total", 0)
        except Exception as e:
            logger.warning("统计原始告警总数失败: %s", e)

        # 6. 摘要文本（Phase 1：AI 综述；无 AI 时模板兜底）
        has_ai = any(
            g.get("ai_model") and g.get("ai_model") != "heuristic" for g in groups
        )
        if has_ai or groups:
            summary = self._build_ai_summary(hours, total, groups, top_assets, ai=has_ai)
        else:
            summary = self._build_summary(hours, total, groups, top_assets)
        svc.close()

        # ai_model 字段：取首个非启发式模型名，否则标记 heuristic
        ai_models = [
            g.get("ai_model") for g in groups if g.get("ai_model") and g.get("ai_model") != "heuristic"
        ]
        ai_model = ai_models[0] if ai_models else ("heuristic" if groups else "template")

        digest = AlertDigest(
            period_type="daily",
            period_start=start,
            period_end=end,
            total_alerts=total,
            by_level=[{"level": b["key"], "count": b["doc_count"]} for b in stats.get("by_level", [])],
            top_groups=groups,
            top_assets=top_assets,
            trend=trend,
            summary_text=summary,
            ai_model=ai_model,
        )
        self.db.add(digest)
        self.db.commit()
        self.db.refresh(digest)
        logger.info("告警摘要已生成: total=%s groups=%s ai_model=%s", total, len(groups), ai_model)
        return digest

    # ── 查询 ─────────────────────────────────────────

    def get_latest(self) -> Optional[AlertDigest]:
        return (
            self.db.query(AlertDigest)
            .order_by(AlertDigest.created_at.desc())
            .first()
        )

    def get_by_date(self, date_str: str) -> Optional[AlertDigest]:
        """按 YYYY-MM-DD 取当天最新一条摘要。"""
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise ValueError("日期格式应为 YYYY-MM-DD")
        start = d.replace(hour=0, minute=0, second=0)
        end = start + timedelta(days=1)
        return (
            self.db.query(AlertDigest)
            .filter(AlertDigest.created_at >= start, AlertDigest.created_at < end)
            .order_by(AlertDigest.created_at.desc())
            .first()
        )

    # ── 内部辅助 ─────────────────────────────────────

    def _enrich_assets(self, top_assets: List[dict]) -> List[dict]:
        """在高频资产上补充资产名/重要度（按 IP 关联 soc_assets）。"""
        from app.models import Asset
        out = []
        for a in top_assets:
            a = dict(a)
            ip = a.get("ip")
            asset = self.db.query(Asset).filter(Asset.asset_ip == ip).first() if ip else None
            if asset:
                a["asset_id"] = str(asset.id)
                a["asset_name"] = asset.name
                a["criticality"] = asset.criticality
            out.append(a)
        return out

    @staticmethod
    def _build_summary(hours, total, groups, top_assets) -> str:
        lines = [f"过去 {hours} 小时共 {total} 条告警，归并为 {len(groups)} 个告警簇。"]
        for i, g in enumerate(groups[:5], 1):
            desc = g.get("rule_description") or f"规则{g.get('rule_id')}"
            target = g.get("agent_name") or g.get("agent_id") or "未知资产"
            lines.append(
                f"Top{i}: 规则 {g.get('rule_id')} {desc} @ {target} "
                f"×{g.get('count')}（等级 {g.get('level_min')}-{g.get('level_max')}）"
            )
        if top_assets:
            lines.append(
                "高频资产: "
                + ", ".join(f"{a.get('asset_name') or a.get('ip')}({a.get('alert_count')})" for a in top_assets[:5])
            )
        return "\n".join(lines)

    @staticmethod
    def _build_ai_summary(hours, total, groups, top_assets, ai: bool = True) -> str:
        """Phase 1 综述：聚焦"今日必处理"（非噪声）的 Top 簇，附优先级/理由/动作。"""
        header = (
            f"过去 {hours} 小时共 {total} 条告警，归并为 {len(groups)} 个告警簇（已 AI 研判 Top{len(groups)}）。"
            if ai
            else f"过去 {hours} 小时共 {total} 条告警，归并为 {len(groups)} 个告警簇（AI 不可用，以下为启发式兜底研判）。"
        )
        lines = [header]

        actionable = [g for g in groups if not g.get("ai_is_noise")]
        if not actionable:
            lines.append("当前 Top 簇均被研判为噪声/良性，可暂不处理，建议关注量级突变。")
        for i, g in enumerate(actionable[:5], 1):
            desc = g.get("rule_description") or f"规则{g.get('rule_id')}"
            target = g.get("agent_name") or g.get("agent_id") or "未知资产"
            lines.append(
                f"必处理 Top{i} [{g.get('ai_priority')}] 规则 {g.get('rule_id')} {desc} @ {target} ×{g.get('count')}"
            )
            if g.get("ai_rationale"):
                lines.append(f"  理由: {g.get('ai_rationale')}")
            if g.get("ai_action"):
                lines.append(f"  建议: {g.get('ai_action')}")
            if g.get("ai_suggest_incident"):
                lines.append("  建议直接建事件单跟进。")

        if top_assets:
            lines.append(
                "高频资产: "
                + ", ".join(f"{a.get('asset_name') or a.get('ip')}({a.get('alert_count')})" for a in top_assets[:5])
            )
        return "\n".join(lines)
