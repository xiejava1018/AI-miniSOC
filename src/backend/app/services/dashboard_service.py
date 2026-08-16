"""
概览仪表板聚合服务

一次返回 KPI 六数 + Δ 环比 + 数据源健康 + 各源新鲜度 + 夜间摘要 + 待办清单 + AI 洞察
（设计文档 docs/design/2026-08-16-概览仪表板设计.md §5.2，聚合接口 dashboard/summary）。

口径要点（与设计文档 §3.2 / 附录 C 对齐）：
- 活跃告警簇：优先 OpenSearch 实时聚合（AlertQueryService.get_alert_groups 的
  total_groups），失败回退 soc_alert_groups 当日（北京时间）distinct fingerprint；
  Δ 环比取快照口径（今日 - 昨日 distinct 指纹数），无基线则为 None。
- 高危漏洞：open + scap 口径（与 /vulnerabilities/stats/overview 完全一致），
  KEV 命中按 upper(cve_id) 关联计数 distinct vulnerability
  （当前为 0，根因是 OS→PG 同步丢老 CVE，见设计文档 §6.1）。
- 行为异常：soc_browsing_events 按 window_end 计窗（不是 created_at）。
- 夜间摘要：昨日 18:00 → 今日 09:00（北京时间）；Python 侧用 zoneinfo 算好
  aware 窗口再传参，不依赖 DB session 时区（soc_alert_groups.first_seen 为
  ISO 文本列，SQL 内 cast 为 timestamptz 后比较）。
- 各模块查询失败时该模块返回 {"error": "..."}，不拖垮整体（显信任原则）。
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import func as sa_func
from sqlalchemy.orm import Session
from sqlalchemy.types import DateTime

from app.core.config import settings
from app.models.ai_analysis import AIAnalysis
from app.models.alert_group_analysis import AlertGroupAnalysis
from app.models.alert_group_snapshot import AlertGroupSnapshot
from app.models.asset import Asset
from app.models.browsing_event import BrowsingEvent
from app.models.cisa_kev import CisaKev
from app.models.incident import Incident
from app.models.vulnerability import AssetVulnerability, Vulnerability

logger = logging.getLogger(__name__)

BJ_TZ = ZoneInfo("Asia/Shanghai")
UTC = timezone.utc

# 探活超时（秒）：轻量 GET/HEAD，超时即视为离线，不阻塞聚合接口
PROBE_TIMEOUT = 3


class DashboardService:
    """概览仪表板聚合服务（get_summary 一次返回全部区块数据）"""

    def __init__(self, db: Session):
        self.db = db

    # ── 主入口 ───────────────────────────────────────

    def get_summary(self) -> Dict[str, Any]:
        """聚合全部仪表板数据；各模块查询失败互不影响。"""
        kpi_builders = [
            ("active_alert_groups", self._kpi_active_alert_groups),
            ("open_incidents", self._kpi_open_incidents),
            ("high_vulns", self._kpi_high_vulns),
            ("browsing_anomalies_24h", self._kpi_browsing_anomalies),
            ("asset_coverage", self._kpi_asset_coverage),
            ("incidents_today", self._kpi_incidents_today),
        ]
        kpi: Dict[str, Any] = {}
        for key, fn in kpi_builders:
            kpi[key] = self._safe(key, fn)

        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "freshness": self._safe("freshness", self._freshness),
            "sources_health": self._safe("sources_health", self._sources_health),
            "kpi": kpi,
            "night_summary": self._safe("night_summary", self._night_summary),
            "todos": self._safe("todos", lambda: self._todos(kpi)),
            "ai_insight": self._safe("ai_insight", self._ai_insight),
        }

    def _safe(self, label: str, fn: Callable[[], Any]) -> Any:
        """显信任原则：单模块失败返回 {"error": ...}，不拖垮整体。"""
        try:
            return fn()
        except Exception as e:
            logger.warning("仪表板模块 %s 查询失败: %s", label, e)
            return {"error": f"{type(e).__name__}: {e}"}

    # ── 数据新鲜度 ───────────────────────────────────

    def _freshness(self) -> Dict[str, Any]:
        """各数据源最近更新时间（PG 核心业务表 max(created_at) + 告警快照最大时间）。"""
        candidates = [
            self.db.query(sa_func.max(Incident.created_at)).scalar(),
            self.db.query(sa_func.max(BrowsingEvent.created_at)).scalar(),
            self.db.query(sa_func.max(AlertGroupAnalysis.created_at)).scalar(),
            self.db.query(sa_func.max(AIAnalysis.created_at)).scalar(),
            self.db.query(sa_func.max(Asset.updated_at)).scalar(),
        ]
        latest = max((d for d in candidates if d is not None), default=None)
        snapshot = self.db.query(sa_func.max(AlertGroupSnapshot.snapshot_at)).scalar()
        return {
            "postgres": latest.isoformat() if latest else None,
            "alert_snapshot": snapshot.isoformat() if snapshot else None,
        }

    # ── 数据源健康（探活）────────────────────────────

    def _sources_health(self) -> Dict[str, Any]:
        """数据源健康药丸：PostgreSQL / OpenSearch / Loki / 采集器纳管数。

        OS / Loki 走轻量探活（httpx GET/HEAD，超时 3s），失败标 online:false
        + error 摘要，不抛异常（显信任原则）。
        """
        health: Dict[str, Any] = {
            "postgres": {"online": True},
            "opensearch": self._probe_opensearch(),
            "loki": self._probe_loki(),
        }
        # 采集器纳管数（与 kpi.asset_coverage 同口径）
        total = self.db.query(sa_func.count(Asset.id)).scalar() or 0
        managed = (
            self.db.query(sa_func.count(Asset.id))
            .filter(Asset.wazuh_agent_id.isnot(None))
            .scalar() or 0
        )
        health["collector"] = {"managed": managed, "total": total}
        return health

    def _probe_opensearch(self) -> Dict[str, Any]:
        """OpenSearch 探活：HEAD / （Wazuh Indexer 自签名证书，verify=False）。"""
        try:
            resp = httpx.head(
                settings.OPENSEARCH_URL.rstrip("/") + "/",
                auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
                verify=False,
                timeout=PROBE_TIMEOUT,
            )
            if resp.status_code < 400:
                return {"online": True}
            return {"online": False, "error": f"HTTP {resp.status_code}"}
        except Exception as e:
            return {"online": False, "error": self._err_summary(e)}

    def _probe_loki(self) -> Dict[str, Any]:
        """Loki 探活：GET /ready（2xx 视为在线；503 等如实暴露 ingester 状态）。"""
        try:
            resp = httpx.get(
                settings.LOKI_API_URL.rstrip("/") + "/ready",
                timeout=PROBE_TIMEOUT,
            )
            if resp.status_code < 400:
                return {"online": True}
            return {
                "online": False,
                "error": f"HTTP {resp.status_code}: {resp.text[:80]}",
            }
        except Exception as e:
            return {"online": False, "error": self._err_summary(e)}

    @staticmethod
    def _err_summary(e: Exception) -> str:
        """异常摘要（截断，避免探活失败把整个接口撑爆）。"""
        msg = f"{type(e).__name__}: {e}"
        return msg[:120]

    # ── KPI：活跃告警簇 ──────────────────────────────

    def _active_alert_groups_from_os(self) -> Optional[int]:
        """OpenSearch 实时聚合活跃簇数（失败返回 None，由调用方走快照回退）。"""
        try:
            from app.services.alert_query import AlertQueryService

            svc = AlertQueryService(self.db)
            try:
                result = svc.get_alert_groups(hours=24, min_count=1, limit=1)
                return int(result.get("total_groups") or 0)
            finally:
                svc.close()
        except Exception as e:
            logger.warning("OS 实时聚合活跃簇失败，回退快照口径: %s", e)
            return None

    def _kpi_active_alert_groups(self) -> Dict[str, Any]:
        """活跃告警簇：OS 实时聚合优先，回退当日（北京时间）快照 distinct 指纹。"""
        # 北京时间"今日 / 昨日"窗口（Python 侧算好，不依赖 DB session 时区）
        now_bj = datetime.now(BJ_TZ)
        today_start = now_bj.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)

        def _distinct_since(start: datetime, end: datetime = None) -> int:
            q = self.db.query(
                sa_func.count(sa_func.distinct(AlertGroupSnapshot.fingerprint))
            ).filter(AlertGroupSnapshot.snapshot_at >= start)
            if end is not None:
                q = q.filter(AlertGroupSnapshot.snapshot_at < end)
            return q.scalar() or 0

        value = self._active_alert_groups_from_os()
        if value is None:
            value = _distinct_since(today_start)

        # Δ 环比：快照口径 今日 distinct - 昨日 distinct（无昨日基线则 None）
        today_n = _distinct_since(today_start)
        yesterday_n = _distinct_since(yesterday_start, today_start)
        delta = (today_n - yesterday_n) if (today_n or yesterday_n) else None

        return {
            "value": value,
            "delta_vs_yesterday": delta,
            "note": "实时聚合 soc_alert_groups 快照 distinct fingerprint",
        }

    # ── KPI：待处置事件 ──────────────────────────────

    def _kpi_open_incidents(self) -> Dict[str, Any]:
        """事件状态分布 + 闭环率（closed / 全部状态事件数）。"""
        rows = (
            self.db.query(Incident.status, sa_func.count(Incident.id))
            .group_by(Incident.status)
            .all()
        )
        counts = {status: cnt for status, cnt in rows}
        total = sum(counts.values())
        closed = counts.get("closed", 0)
        return {
            "value": counts.get("open", 0),
            "in_progress": counts.get("in_progress", 0),
            "closed": closed,
            "closure_rate": round(closed / total, 3) if total else 0.0,
        }

    # ── KPI：高危漏洞（open + scap 口径）────────────

    def _kpi_high_vulns(self) -> Dict[str, Any]:
        """未修复高危漏洞：critical+high 之和，口径与 /vulnerabilities/stats/overview
        完全一致（join soc_asset_vulnerabilities + soc_vulnerabilities，
        status=open, type='scap'）；KEV 命中按 upper(cve_id) left join 计数。
        """
        rows = (
            self.db.query(Vulnerability.severity, sa_func.count(AssetVulnerability.id))
            .join(
                AssetVulnerability,
                AssetVulnerability.vulnerability_id == Vulnerability.id,
            )
            .filter(
                AssetVulnerability.status == "open",
                Vulnerability.type == "scap",
            )
            .group_by(Vulnerability.severity)
            .all()
        )
        sev = {s: c for s, c in rows}
        critical = sev.get("critical", 0)
        high = sev.get("high", 0)

        kev_hits = (
            self.db.query(sa_func.count(sa_func.distinct(Vulnerability.id)))
            .join(
                AssetVulnerability,
                AssetVulnerability.vulnerability_id == Vulnerability.id,
            )
            .outerjoin(
                CisaKev,
                sa_func.upper(CisaKev.cve_id) == sa_func.upper(Vulnerability.cve_id),
            )
            .filter(
                AssetVulnerability.status == "open",
                Vulnerability.type == "scap",
                CisaKev.cve_id.isnot(None),
            )
            .scalar() or 0
        )

        return {
            "value": critical + high,
            "critical": critical,
            "high": high,
            "kev_hits": kev_hits,
            "kev_note": "OS→PG 同步丢老 CVE，待修",
        }

    # ── KPI：行为异常（24h，按 window_end）──────────

    def _kpi_browsing_anomalies(self) -> Dict[str, Any]:
        """近 24h 行为异常数 / 累计 / 前 24h（时间列是 window_end，不是 created_at）。"""
        now = datetime.now(UTC)
        last24 = now - timedelta(hours=24)
        prev48 = now - timedelta(hours=48)

        cur = (
            self.db.query(sa_func.count(BrowsingEvent.id))
            .filter(BrowsingEvent.window_end > last24)
            .scalar() or 0
        )
        prev = (
            self.db.query(sa_func.count(BrowsingEvent.id))
            .filter(
                BrowsingEvent.window_end > prev48,
                BrowsingEvent.window_end <= last24,
            )
            .scalar() or 0
        )
        total = self.db.query(sa_func.count(BrowsingEvent.id)).scalar() or 0
        return {"value": cur, "total": total, "prev_24h": prev}

    # ── KPI：资产纳管率 ──────────────────────────────

    def _kpi_asset_coverage(self) -> Dict[str, Any]:
        """资产纳管率：wazuh_agent_id 非空为已纳管；未纳管按 criticality 分档。"""
        total = self.db.query(sa_func.count(Asset.id)).scalar() or 0
        managed = (
            self.db.query(sa_func.count(Asset.id))
            .filter(Asset.wazuh_agent_id.isnot(None))
            .scalar() or 0
        )
        rows = (
            self.db.query(Asset.criticality, sa_func.count(Asset.id))
            .filter(Asset.wazuh_agent_id.is_(None))
            .group_by(Asset.criticality)
            .all()
        )
        return {
            "managed": managed,
            "total": total,
            "rate": round(managed / total, 3) if total else 0.0,
            "unmanaged_by_criticality": {c: n for c, n in rows},
        }

    # ── KPI：今日新增事件 ────────────────────────────

    def _kpi_incidents_today(self) -> Dict[str, Any]:
        """今日（北京时间）新增事件 + 近 7 天事件数。"""
        now = datetime.now(UTC)
        today_start_bj = datetime.now(BJ_TZ).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today = (
            self.db.query(sa_func.count(Incident.id))
            .filter(Incident.created_at >= today_start_bj)
            .scalar() or 0
        )
        last7 = (
            self.db.query(sa_func.count(Incident.id))
            .filter(Incident.created_at >= now - timedelta(days=7))
            .scalar() or 0
        )
        return {"value": today, "last_7d": last7}

    # ── 夜间摘要（昨日 18:00 → 今日 09:00 北京时间）──

    @staticmethod
    def _night_window() -> tuple:
        """夜间窗口 [start, end)：昨日 18:00 → 今日 09:00（北京时间），返回 aware UTC。"""
        now_bj = datetime.now(BJ_TZ)
        start_bj = (now_bj - timedelta(days=1)).replace(
            hour=18, minute=0, second=0, microsecond=0
        )
        end_bj = now_bj.replace(hour=9, minute=0, second=0, microsecond=0)
        return start_bj.astimezone(UTC), end_bj.astimezone(UTC)

    def _night_summary(self) -> Dict[str, Any]:
        """夜间摘要：新增告警簇 / 新增事件 / 高危行为 / KEV 漏洞新增。"""
        start, end = self._night_window()

        # soc_alert_groups.first_seen 是 ISO 文本列，cast 成 timestamptz 再比窗口
        first_seen_ts = sa_func.cast(
            AlertGroupSnapshot.first_seen, DateTime(timezone=True)
        )
        new_groups = (
            self.db.query(
                sa_func.count(sa_func.distinct(AlertGroupSnapshot.fingerprint))
            )
            .filter(first_seen_ts >= start, first_seen_ts < end)
            .scalar() or 0
        )
        new_incidents = (
            self.db.query(sa_func.count(Incident.id))
            .filter(Incident.created_at >= start, Incident.created_at < end)
            .scalar() or 0
        )
        browsing = (
            self.db.query(sa_func.count(BrowsingEvent.id))
            .filter(BrowsingEvent.window_end >= start, BrowsingEvent.window_end < end)
            .scalar() or 0
        )
        kev_new = (
            self.db.query(sa_func.count(CisaKev.cve_id))
            .filter(CisaKev.date_added >= start, CisaKev.date_added < end)
            .scalar() or 0
        )
        return {
            "new_alert_groups": new_groups,
            "new_incidents": new_incidents,
            "browsing_anomalies": browsing,
            "kev_new": kev_new,
        }

    # ── 我的待办（今日优先处置清单）──────────────────

    def _todos(self, kpi: Dict[str, Any]) -> list:
        """待办清单：顺序固定（资产纳管→事件积压→行为复核→AI覆盖），文案动态生成。

        - 资产纳管：数字来自 kpi.asset_coverage.unmanaged_by_criticality，
          normal 档不进待办（噪音大于价值，设计文档附录 A-5）；无未纳管则不出
        - 事件积压：最老 N 天动态算 (now - min(created_at where status=open)).days
        - 行为复核：近 24h 为 0 则不出
        """
        todos: list = []

        # 1. 资产纳管（紧急）
        un = (kpi.get("asset_coverage") or {}).get("unmanaged_by_criticality") or {}
        parts = [
            f"{un[level]} 台 {level}"
            for level in ("critical", "high", "medium", "low")
            if (un.get(level) or 0) > 0
        ]
        if parts:
            todos.append({
                "id": "asset_coverage",
                "priority": "p0",
                "title": "高关键资产未纳管 + 中关键资产未纳管",
                "detail": " + ".join(parts) + " 无 agent",
                "action": "按 criticality 排序排程补装",
            })

        # 2. 事件积压（高）
        open_n = (kpi.get("open_incidents") or {}).get("value") or 0
        if open_n > 0:
            oldest = (
                self.db.query(sa_func.min(Incident.created_at))
                .filter(Incident.status == "open")
                .scalar()
            )
            days = (
                (datetime.now(UTC) - oldest).days if oldest is not None else 0
            )
            todos.append({
                "id": "incident_backlog",
                "priority": "p1",
                "title": "事件积压",
                "detail": f"{open_n} 起 open，最老 {days} 天未处理",
                "action": "按 created_at 升序清理",
            })

        # 3. 行为复核（中）：近 24h 为 0 则不出
        n24 = (kpi.get("browsing_anomalies_24h") or {}).get("value") or 0
        if n24 > 0:
            todos.append({
                "id": "browsing_review",
                "priority": "p2",
                "title": "行为偏离待复核",
                "detail": f"近 24h {n24} 起异常",
                "action": "进入行为事件页复核",
            })

        # 4. AI 覆盖（中）：X = soc_ai_analyses 条数，Y = soc_alert_group_analyses 簇数
        try:
            single = self.db.query(sa_func.count(AIAnalysis.id)).scalar() or 0
            group = self.db.query(sa_func.count(AlertGroupAnalysis.id)).scalar() or 0
            todos.append({
                "id": "ai_coverage",
                "priority": "p2",
                "title": "个警 AI 研判覆盖低",
                "detail": f"仅 {single} 条 vs 群体 {group} 簇",
                "action": "在告警治理页触发研判",
            })
        except Exception as e:  # 极端情况下跳过该条，不影响其余待办
            logger.warning("AI 覆盖待办统计失败: %s", e)

        return todos

    # ── AI 洞察 ──────────────────────────────────────

    def _ai_insight(self) -> Dict[str, Any]:
        """AI 洞察：覆盖率小标签 + Top3 非噪声簇研判建议。

        top_groups 从 soc_alert_group_analyses 取 is_noise=false，按
        priority（P0<P1<P2<P3）+ created_at desc 排序，limit 3；
        agent_ip 从 soc_alert_groups 按 fingerprint 取最新快照行。
        """
        group_n = (
            self.db.query(sa_func.count(AlertGroupAnalysis.id)).scalar() or 0
        )
        single_n = self.db.query(sa_func.count(AIAnalysis.id)).scalar() or 0

        rows = (
            self.db.query(AlertGroupAnalysis)
            .filter(AlertGroupAnalysis.is_noise.is_(False))
            .order_by(
                AlertGroupAnalysis.priority.asc(),
                AlertGroupAnalysis.created_at.desc(),
            )
            .limit(3)
            .all()
        )

        # fingerprint -> 最新快照行的 agent_ip（一次查询取回后按序取首个非空）
        ip_map: Dict[str, str] = {}
        fps = [r.fingerprint for r in rows if r.fingerprint]
        if fps:
            snaps = (
                self.db.query(
                    AlertGroupSnapshot.fingerprint, AlertGroupSnapshot.agent_ip
                )
                .filter(AlertGroupSnapshot.fingerprint.in_(fps))
                .order_by(AlertGroupSnapshot.snapshot_at.desc())
                .all()
            )
            for fp, ip in snaps:
                if ip and fp not in ip_map:
                    ip_map[fp] = ip

        top_groups = [
            {
                "fingerprint": r.fingerprint,
                "rule_description": r.rule_description,
                "agent_id": r.agent_id,
                "agent_ip": ip_map.get(r.fingerprint),
                "priority": r.priority,
                "confidence": r.confidence,
                "recommended_action": (r.recommended_action or "")[:200],
            }
            for r in rows
        ]
        return {
            "coverage": {
                "group_analyses": group_n,
                "single_analyses": single_n,
            },
            "top_groups": top_groups,
        }
