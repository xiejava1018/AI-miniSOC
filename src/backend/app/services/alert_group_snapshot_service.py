"""
告警簇快照服务（方案 B）

- snapshot(): 调 AlertQueryService.get_alert_groups 取全量簇，
  按 agent_ip 关联 soc_assets 后批量写 soc_alert_groups。
- query_history(): 历史列表（按日期 / 资产 / 等级过滤）。
- get_trend(): 按天聚合，供趋势图。
- cleanup_retention(): 仅保留最近 N 天。
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func as sa_func, delete

from app.core.database import SessionLocal
from app.models.alert_group_snapshot import AlertGroupSnapshot
from app.models.alert_group_analysis import AlertGroupAnalysis
from app.models.asset import Asset
from app.services.alert_query import AlertQueryService

logger = logging.getLogger(__name__)

RETENTION_DAYS = 90
SNAPSHOT_WINDOW_HOURS = 24

# 模块级一次性标记：确保 soc_alert_groups 的 AI 列已存在
# （create_all 不会给已存在的表加列，需显式 ALTER）
_schema_ensured = False


class AlertGroupSnapshotService:
    def __init__(self, db):
        self.db = db

    def _ensure_schema(self) -> None:
        """确保 soc_alert_groups 的 AI 列存在（create_all 不会给已存在表加列）。"""
        global _schema_ensured
        if _schema_ensured:
            return
        from app.core.database import engine
        from app.models.base import Base
        from sqlalchemy import text

        Base.metadata.create_all(
            bind=engine,
            tables=[AlertGroupSnapshot.__table__, AlertGroupAnalysis.__table__],
            checkfirst=True,
        )
        for col, typ in (
            ("ai_priority", "VARCHAR(4)"),
            ("ai_is_noise", "BOOLEAN"),
            ("ai_suggest_incident", "BOOLEAN"),
            ("ai_verdict_at", "TIMESTAMPTZ"),
        ):
            try:
                self.db.execute(
                    text(f"ALTER TABLE soc_alert_groups ADD COLUMN IF NOT EXISTS {col} {typ}")
                )
            except Exception as e:  # 列已存在等
                logger.warning("确保 AI 列失败(%s): %s", col, e)
        self.db.commit()
        _schema_ensured = True

    def snapshot(self, hours: int = SNAPSHOT_WINDOW_HOURS) -> dict:
        """对当前窗口的告警簇做全量快照，写入 soc_alert_groups。

        Phase 1：落库时为每簇按 fingerprint 回填"最近一次 AI verdict"（不重新调 AI）。
        """
        self._ensure_schema()
        svc = AlertQueryService(self.db)
        result = svc.get_alert_groups(hours=hours, min_count=1, level=None, limit=500)
        groups = result.get("groups", []) if isinstance(result, dict) else result

        # 回填 verdict：按 fingerprint 批量取缓存（零额外 AI 配额）
        verdict_map: dict = {}
        fps = [g.get("fingerprint") for g in groups if g.get("fingerprint")]
        if fps:
            objs = (
                self.db.query(AlertGroupAnalysis)
                .filter(AlertGroupAnalysis.fingerprint.in_(fps))
                .all()
            )
            for o in objs:
                verdict_map[o.fingerprint] = o

        asset_map = self._build_asset_map()
        snapshot_at = datetime.now(timezone.utc)
        rows = []
        for g in groups:
            agent_ip = g.get("agent_ip")
            asset = asset_map.get(agent_ip) if agent_ip else None
            v = verdict_map.get(g.get("fingerprint"))
            rows.append(AlertGroupSnapshot(
                snapshot_at=snapshot_at,
                window_hours=hours,
                fingerprint=g.get("fingerprint"),
                rule_id=str(g.get("rule_id")) if g.get("rule_id") is not None else None,
                rule_description=g.get("rule_description"),
                agent_id=g.get("agent_id"),
                agent_name=g.get("agent_name"),
                agent_ip=agent_ip,
                count=g.get("count") or 0,
                level_min=g.get("level_min"),
                level_max=g.get("level_max"),
                first_seen=g.get("first_seen"),
                last_seen=g.get("last_seen"),
                distinct_srcips=g.get("distinct_srcips"),
                top_srcips=g.get("top_srcips"),
                linked_asset_id=asset.id if asset else None,
                # —— 回填的 AI verdict ——
                ai_priority=v.priority if v else None,
                ai_is_noise=v.is_noise if v else None,
                ai_suggest_incident=v.suggest_incident if v else None,
                ai_verdict_at=v.created_at if v else None,
            ))
        if rows:
            self.db.bulk_save_objects(rows)
            self.db.commit()
        linked = sum(1 for r in rows if r.linked_asset_id)
        triaged = sum(1 for r in rows if r.ai_priority)
        logger.info(
            "alert group snapshot: at=%s hours=%d groups=%d linked=%d triaged=%d",
            snapshot_at.isoformat(), hours, len(rows), linked, triaged,
        )
        return {
            "snapshot_at": snapshot_at.isoformat(),
            "hours": hours,
            "groups_snapshotted": len(rows),
            "assets_linked": linked,
            "ai_triaged": triaged,
        }

    def _build_asset_map(self) -> dict:
        """agent_ip -> Asset 映射（一次查询全表，资产量不大）。"""
        m = {}
        for a in self.db.query(Asset).all():
            if a.asset_ip:
                m[a.asset_ip] = a
        return m

    def query_history(
        self,
        date: Optional[str] = None,
        asset_ip: Optional[str] = None,
        level: Optional[int] = None,
        limit: int = 500,
    ) -> list:
        stmt = select(AlertGroupSnapshot)
        if date:
            stmt = stmt.where(sa_func.date(AlertGroupSnapshot.snapshot_at) == date)
        if asset_ip:
            stmt = stmt.where(AlertGroupSnapshot.agent_ip == asset_ip)
        if level is not None:
            stmt = stmt.where(AlertGroupSnapshot.level_max >= level)
        stmt = stmt.order_by(
            AlertGroupSnapshot.snapshot_at.desc(),
            AlertGroupSnapshot.count.desc(),
        ).limit(limit)
        return self.db.execute(stmt).scalars().all()

    def get_trend(self, days: int = 14) -> dict:
        """按 snapshot 日期聚合：每日簇数 / 告警总量 / 关联资产数。"""
        since = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = (
            select(
                sa_func.date(AlertGroupSnapshot.snapshot_at).label("day"),
                sa_func.count().label("clusters"),
                sa_func.sum(AlertGroupSnapshot.count).label("alerts"),
                sa_func.count(AlertGroupSnapshot.linked_asset_id).label("linked"),
            )
            .where(AlertGroupSnapshot.snapshot_at >= since)
            .group_by(sa_func.date(AlertGroupSnapshot.snapshot_at))
            .order_by("day")
        )
        rows = self.db.execute(stmt).all()
        days_out = [{
            "date": str(r.day),
            "clusters": r.clusters,
            "alerts": int(r.alerts or 0),
            "linked_assets": r.linked,
        } for r in rows]
        return {"days": days_out, "span_days": days}

    def cleanup_retention(self, days: int = RETENTION_DAYS) -> int:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = delete(AlertGroupSnapshot).where(AlertGroupSnapshot.snapshot_at < cutoff)
        res = self.db.execute(stmt)
        self.db.commit()
        return res.rowcount or 0
