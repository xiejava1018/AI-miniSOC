"""
AI 安全报告生成器（PRD P3 / F2.2）

职责边界（对齐 §1.3 / §八-B 设计原则）：
  - 报告 = 把已有数据讲成运维可读的话，**不预测、不编造**
  - 数据完整性校验是硬门槛——窗口内数据缺任何一段都必须在 data_coverage.gaps 显式标注
  - AI 只生成 summary / risk_highlights / recommendations 三段；overview/trends/risks 章节
    由 _build_content() 直接由数据生成，AI 没有可乘之机

数据来源：
  - PostgreSQL: soc_assets（在线率/风险分布/Top5）、soc_asset_reconciliations（对账差异数）、
               soc_source_health（源健康）
  - OpenSearch : wazuh-alerts-4.x-* （走 AlertQueryService.get_alerts(level, time range)）

触发类型：
  - weekly / monthly : 固定过去 N 天窗口
  - on_demand       : 调用方传 period_start/end
  - incident_driven : 过去 24h critical+high ≥ 阈值时自动生成

降级策略（与 reconcile_ai 一致）：
  - ai_budget 限流 / GLM Key 缺失 / 调用失败 → _template_report()
  - data_coverage.data_degraded=True 时 AI 文案必须开头先声明

事件驱动实现（务实降级，不引入消息队列）：
  - check_incident_trigger() 同步方法供 cron 调用或前端按钮触发
  - 触发即落库一份 incident_driven 报告
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Asset,
    AssetReconciliation,
    SecurityReport,
    SourceHealth,
)
from app.models.security_report import (
    REPORT_TYPES,
    TYPE_INCIDENT_DRIVEN,
    TYPE_MONTHLY,
    TYPE_ON_DEMAND,
    TYPE_WEEKLY,
)
from app.services.ai_budget import ai_budget
from app.services.alert_query import AlertQueryService
from app.services.asset_risk import AssetRiskService

logger = logging.getLogger(__name__)

PROMPT_VERSION = "security-report-v1"

# Wazuh rule.level 标准阈值
#   level >= 13 → critical  (Fidelity > 9)
#   level >= 10 → high      (Fidelity > 8)
#   level >=  7 → medium
#   level >=  4 → low
CRITICAL_LEVEL = 13
HIGH_LEVEL = 10

# 默认窗口
WINDOW_DAYS = {"weekly": 7, "monthly": 30}
LOKI_RETENTION_DAYS = 7  # 写死在 §八-B；超出窗口数据视为"丢失"

# 默认配置（可被 soc_system_config(category='reports') 覆盖）
DEFAULT_INCIDENT_THRESHOLD = 3
DEFAULT_INCIDENT_WINDOW_HOURS = 24


# ---------------------------------------------------------------------------
# 小工具：报告生成前的配置/窗口/数据完整性
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _resolve_window(report_type: str, now: datetime,
                    period_start: Optional[datetime],
                    period_end: Optional[datetime]) -> tuple[datetime, datetime]:
    """根据 report_type 返回 (start, end) UTC。

    on_demand 必须显式传 period_start/period_end；其他类型按默认值。
    """
    if report_type == TYPE_ON_DEMAND:
        if not period_start or not period_end:
            raise ValueError("on_demand 类型必须显式传 period_start 与 period_end")
        return period_start, period_end
    if report_type == TYPE_INCIDENT_DRIVEN:
        # 触发窗口固定过去 24h；调用方已在 check_incident_trigger 里决定
        return now - timedelta(hours=DEFAULT_INCIDENT_WINDOW_HOURS), now
    days = WINDOW_DAYS.get(report_type)
    if not days:
        raise ValueError(f"未知 report_type: {report_type}")
    return now - timedelta(days=days), now


def _get_config(db: Session, key: str, default):
    """读 soc_system_config(category='reports', key=...)；缺则回退默认。"""
    row = db.execute(
        select(__import__("app.models", fromlist=["SystemConfig"]).SystemConfig)
        .where(
            __import__("app.models", fromlist=["SystemConfig"]).SystemConfig.category == "reports",
            __import__("app.models", fromlist=["SystemConfig"]).SystemConfig.key == key,
        )
    ).scalar_one_or_none()
    if row is None:
        return default
    try:
        return type(default)(row.value)
    except (TypeError, ValueError):
        return default


def _data_coverage(db: Session, start: datetime, end: datetime,
                   opensearch_ok: bool, opensearch_error: Optional[str]) -> dict:
    """生成 data_coverage 字段——PRD 硬门槛。

    即使 AI 调用失败也必须落库这段，运维要看到「报告覆盖了哪些数据、丢了哪些」。
    """
    sources = db.execute(select(SourceHealth)).scalars().all()
    source_summary = []
    has_overdue = False
    for s in sources:
        # SourceHealth 的字段：source_key, source_type, last_success_at, last_failure_message,
        #   last_failure_at, success_count, failure_count, expected_interval_seconds
        overdue = False
        reason = None
        if s.expected_interval_seconds and s.last_success_at:
            age = (_utcnow() - s.last_success_at).total_seconds()
            if age > s.expected_interval_seconds * 3:  # 3 倍间隔未更新 → overdue
                overdue = True
                has_overdue = True
                reason = f"已 {(age/3600):.1f} 小时无成功记录（预期间隔 {s.expected_interval_seconds}s）"
        elif not s.last_success_at:
            overdue = True
            has_overdue = True
            reason = "从未成功采集"
        source_summary.append({
            "source_key": s.source_key,
            "source_type": s.source_type,
            "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
            "overdue": overdue,
            "reason": reason,
        })

    window_hours = (end - start).total_seconds() / 3600
    gaps = []
    if not opensearch_ok:
        gaps.append({
            "scope": "alert_trends",
            "reason": f"OpenSearch 不可达：{opensearch_error or '未知'}",
            "impact": "告警趋势章节将使用零值，**禁止解读为「无告警」**",
        })
    if window_hours / 24 > LOKI_RETENTION_DAYS:
        gaps.append({
            "scope": "loki_logs",
            "reason": f"报告窗口 {window_hours/24:.1f} 天超过 Loki {LOKI_RETENTION_DAYS} 天保留期",
            "impact": "窗口前段的上网行为日志已不可查（仅靠 OpenSearch 告警）",
        })
    if has_overdue:
        bad = [s["source_key"] for s in source_summary if s["overdue"]]
        gaps.append({
            "scope": "data_sources",
            "reason": f"数据源过期：{', '.join(bad)}",
            "impact": "对应源相关的数据为陈旧值",
        })

    return {
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "window_hours": round(window_hours, 1),
        "opensearch_available": opensearch_ok,
        "opensearch_error": opensearch_error,
        "source_health": source_summary,
        "gaps": gaps,
        "data_degraded": bool(gaps),
        "generated_at": _utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# 主服务
# ---------------------------------------------------------------------------

class SecurityReportService:
    """AI 安全报告生成器"""

    def __init__(self, db: Session):
        self.db = db
        self.alert_svc = AlertQueryService(db)
        self.risk_svc = AssetRiskService(db)

    # ---------- 主入口 ----------

    def generate(
        self,
        report_type: str,
        triggered_by: str,
        period_start: Optional[datetime] = None,
        period_end: Optional[datetime] = None,
        force_glm: bool = True,
    ) -> SecurityReport:
        if report_type not in REPORT_TYPES:
            raise ValueError(f"report_type 须为 {sorted(REPORT_TYPES)} 之一")
        now = _utcnow()
        start, end = _resolve_window(report_type, now, period_start, period_end)

        # 1. 数据完整性探针：先跑告警查询确认 OpenSearch 可达
        opensearch_ok, opensearch_error, alerts_by_level = self._collect_alert_trends(start, end)

        # 2. 收集事实
        facts = self._collect_facts(start, end, opensearch_ok, alerts_by_level)

        # 3. data_coverage（无论 AI 是否降级都落库）
        coverage = _data_coverage(self.db, start, end, opensearch_ok, opensearch_error)

        # 4. content 章节（纯模板拼装，不依赖 AI）
        content = self._build_content(facts, coverage)

        # 5. AI 三段
        if force_glm:
            text, source = self._glm_report(facts, coverage)
            if text is None:
                text = self._template_report(facts, coverage)
                source = "template"
        else:
            text = self._template_report(facts, coverage)
            source = "template"

        # 6. 落库
        title = self._build_title(report_type, start, end, facts)
        report = SecurityReport(
            id=uuid.uuid4(),
            report_type=report_type,
            period_start=start,
            period_end=end,
            title=title,
            summary=text.get("summary", ""),
            content=content,
            risk_highlights=text.get("risk_highlights", ""),
            recommendations=text.get("recommendations", ""),
            data_coverage=coverage,
            prompt_version=PROMPT_VERSION,
            triggered_by=triggered_by,
            trigger_meta=text.get("trigger_meta"),
            created_at=now,
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report

    # ---------- 事件驱动触发检查 ----------

    def check_incident_trigger(self, triggered_by: str = "system:scheduler") -> Optional[SecurityReport]:
        """过去 24h 累计 critical+high ≥ 阈值时自动生成 incident_driven 报告。

        用于：cron / 前端手动按钮。返回生成的报告或 None（未达阈值）。
        """
        threshold = _get_config(self.db, "incident_threshold", DEFAULT_INCIDENT_THRESHOLD)
        now = _utcnow()
        start = now - timedelta(hours=DEFAULT_INCIDENT_WINDOW_HOURS)
        opensearch_ok, err, alerts_by_level = self._collect_alert_trends(start, now)
        crit_high = alerts_by_level.get("critical", 0) + alerts_by_level.get("high", 0)
        if crit_high < threshold:
            return None
        report = self.generate(
            report_type=TYPE_INCIDENT_DRIVEN,
            triggered_by=triggered_by,
            period_start=start,
            period_end=now,
            force_glm=True,
        )
        # trigger_meta 已在 generate 内被覆盖，这里补实际数字
        if report.trigger_meta is None:
            report.trigger_meta = {}
        report.trigger_meta = {
            "critical_high_count": crit_high,
            "threshold": threshold,
            "window_hours": DEFAULT_INCIDENT_WINDOW_HOURS,
        }
        self.db.commit()
        return report

    # ---------- 列表 / 详情 ----------

    def list(self, report_type: Optional[str] = None, page: int = 1,
             page_size: int = 20) -> dict:
        q = select(SecurityReport).order_by(SecurityReport.created_at.desc())
        if report_type:
            q = q.where(SecurityReport.report_type == report_type)
        total = self.db.execute(
            select(func.count()).select_from(q.subquery())
        ).scalar() or 0
        rows = self.db.execute(
            q.offset((max(1, page) - 1) * page_size).limit(page_size)
        ).scalars().all()
        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "records": [self._serialize(r) for r in rows],
        }

    def latest(self, report_type: str) -> Optional[dict]:
        r = self.db.execute(
            select(SecurityReport)
            .where(SecurityReport.report_type == report_type)
            .order_by(SecurityReport.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        return self._serialize(r) if r else None

    def get(self, report_id: uuid.UUID) -> Optional[dict]:
        r = self.db.get(SecurityReport, report_id)
        return self._serialize(r) if r else None

    # ---------- 数据收集 ----------

    def _collect_alert_trends(self, start: datetime, end: datetime) -> tuple[bool, Optional[str], dict]:
        """从 OpenSearch 拉窗口内告警，按 rule.level 分桶。

        返回 (ok, error, {critical, high, medium, low, total})。
        """
        try:
            # critical+high 都拉，再在内存分桶（rule.level 是数值，单次查询够用）
            resp = self.alert_svc.get_alerts(
                offset=0,
                limit=10000,        # 单次最多 1 万，PRD 规模足够
                level=CRITICAL_LEVEL - 3,  # 抓 ≥ 10 足以覆盖 critical+high
                start_time=start,
                end_time=end,
                sort_by="@timestamp",
                sort_order="desc",
            )
        except httpx.HTTPError as exc:
            return False, f"OpenSearch HTTP 错误: {exc.__class__.__name__}", {}
        except Exception as exc:
            return False, f"OpenSearch 查询失败: {exc.__class__.__name__}: {exc}", {}

        items = resp.get("items") or []
        buckets = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for it in items:
            lv = (it.get("rule") or {}).get("level") or 0
            if lv >= CRITICAL_LEVEL:
                buckets["critical"] += 1
            elif lv >= HIGH_LEVEL:
                buckets["high"] += 1
            elif lv >= 7:
                buckets["medium"] += 1
            elif lv >= 4:
                buckets["low"] += 1
        buckets["total"] = sum(v for k, v in buckets.items() if k != "total")
        return True, None, buckets

    def _collect_facts(self, start: datetime, end: datetime,
                       opensearch_ok: bool, alerts_by_level: dict) -> dict:
        # 资产总览
        total = self.db.execute(select(func.count(Asset.id))).scalar() or 0
        online = self.db.execute(
            select(func.count(Asset.id)).where(Asset.asset_status == "online")
        ).scalar() or 0

        # 风险分布
        risk = self.risk_svc.overview() if hasattr(self.risk_svc, "overview") else {}
        risk_buckets = risk.get("buckets") or {}
        risk_top10 = risk.get("top10") or []

        # 对账差异数（最近批次）
        recon_pending = self.db.execute(
            select(func.count(AssetReconciliation.id))
            .where(AssetReconciliation.status == "pending")
        ).scalar() or 0

        return {
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "window_days": (end - start).days,
            "asset_total": total,
            "asset_online": online,
            "online_rate": round(online / total * 100, 1) if total else 0.0,
            "risk_buckets": risk_buckets,
            "risk_top5": risk_top10[:5],
            "alert_buckets": alerts_by_level if opensearch_ok else {
                "critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0,
                "_unavailable": True,
            },
            "alert_opensearch_ok": opensearch_ok,
            "reconciliation_pending": recon_pending,
        }

    # ---------- content 章节（纯模板，不走 AI） ----------

    def _build_content(self, facts: dict, coverage: dict) -> dict:
        """四章节 + data_notes，全部由事实拼装——AI 无法影响。"""
        online = facts["asset_total"]
        online_pct = facts["online_rate"]
        risk = facts["risk_buckets"]
        alerts = facts["alert_buckets"]
        top5 = facts["risk_top5"]

        # ---- 总览 ----
        overview_lines = [
            f"资产总数 {online} 台，在线 {facts['asset_online']} 台（在线率 {online_pct}%）",
            f"风险分布：critical {risk.get('critical', 0)} / high {risk.get('high', 0)} / "
            f"medium {risk.get('medium', 0)} / low {risk.get('low', 0)} / "
            f"未评分 {risk.get('na', 0)}",
        ]
        if alerts.get("_unavailable"):
            overview_lines.append("告警趋势：OpenSearch 不可用，详见数据说明")
        else:
            overview_lines.append(
                f"告警数：critical {alerts.get('critical', 0)} / high {alerts.get('high', 0)} / "
                f"medium {alerts.get('medium', 0)} / low {alerts.get('low', 0)} / "
                f"合计 {alerts.get('total', 0)}"
            )
        if facts["reconciliation_pending"]:
            overview_lines.append(
                f"台账对账：{facts['reconciliation_pending']} 项差异待处理（详情见「数据健康」页）"
            )

        # ---- 风险 Top5 ----
        risks_lines = []
        for a in top5:
            risks_lines.append(
                f"- {a.get('name', '（未命名）')[:28]} {a.get('ip', '')} "
                f"风险分 {a.get('risk_score', '?')} "
                f"{(a.get('risk_summary') or '')[:60]}"
            )
        if not risks_lines:
            risks_lines.append("（无可展示的高风险资产）")

        # ---- 趋势 ----
        if alerts.get("_unavailable"):
            trends_lines = ["OpenSearch 不可用，告警趋势数据为空（详见数据说明）"]
        else:
            trends_lines = [
                f"窗口 {facts['window_days']} 天内告警合计 {alerts.get('total', 0)} 条",
                f"其中高危（critical+high）{alerts.get('critical', 0) + alerts.get('high', 0)} 条",
            ]

        # ---- 处置建议（占位，AI 写入） ----
        # ---- 数据说明 ----
        notes_lines = []
        notes_lines.append(f"窗口：{facts['window_days']} 天（{facts['window_start']} ~ {facts['window_end']}）")
        for g in coverage.get("gaps") or []:
            notes_lines.append(f"- {g['scope']}：{g['reason']}（影响：{g['impact']}）")
        if not coverage.get("gaps"):
            notes_lines.append("数据完整，无缺口")

        return {
            "overview": "\n".join(overview_lines),
            "trends": "\n".join(trends_lines),
            "risks": "\n".join(risks_lines),
            "data_notes": "\n".join(notes_lines),
        }

    def _build_title(self, report_type: str, start: datetime, end: datetime, facts: dict) -> str:
        label = {
            TYPE_WEEKLY: "周报",
            TYPE_MONTHLY: "月报",
            TYPE_ON_DEMAND: "按需报告",
            TYPE_INCIDENT_DRIVEN: "事件驱动报告",
        }.get(report_type, report_type)
        return f"{label} · {facts['window_days']}天 · {facts['asset_total']}台资产"

    # ---------- AI 报告 / 模板降级 ----------

    def _glm_report(self, facts: dict, coverage: dict) -> tuple[Optional[dict], str]:
        if not ai_budget.allow():
            logger.info("安全报告降级为模板：AI 预算/限流不允许")
            return None, "template"
        if not getattr(settings, "GLM_API_KEY", None):
            return None, "template"
        try:
            from zhipuai import ZhipuAI

            facts_str = "\n".join(f"{k}: {v}" for k, v in facts.items())
            coverage_str = "\n".join(
                f"  - {g['scope']}: {g['reason']}" for g in (coverage.get("gaps") or [])
            ) or "  （无缺口）"

            sys_prompt = (
                "你是 AI-miniSOC 安全运营助手。基于给定事实生成结构化报告，"
                "要求严格遵守以下规则：\n"
                "1) 不得推测未提供的信息；如数据不在事实里，写「数据不足」\n"
                "2) data_degraded=True 时，summary 必须开头先声明「数据可信度降级，结果可能不全」\n"
                "3) summary ≤ 200 字（纯文本，一段话）；risk_highlights / recommendations 用短横线列表（每行以 - 开头，**不要** 用 JSON 数组、Markdown 代码块或编号列表）\n"
                "4) 推荐事项要可执行（例如「联系 xxx 工单」「检查 xxx 配置」），不写空话\n"
                "5) 输出严格 JSON：{\"summary\": \"字符串\", \"risk_highlights\": \"多行字符串\", \"recommendations\": \"多行字符串\"}"
            )
            user_prompt = (
                f"【事实】\n{facts_str}\n\n"
                f"【数据完整性】\ndata_degraded={coverage.get('data_degraded')}\n"
                f"缺口：\n{coverage_str}"
            )

            client = ZhipuAI(api_key=settings.GLM_API_KEY)
            resp = client.chat.completions.create(
                model=getattr(settings, "GLM_MODEL", "glm-4-flash"),
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=900,
            )
            text = (resp.choices[0].message.content or "").strip()
            ai_budget.record_success()
            parsed = self._parse_glm_json(text)
            if parsed:
                return parsed, "glm"
        except Exception as exc:  # noqa: BLE001 — AI 失败绝不阻塞报告生成
            ai_budget.record_failure()
            logger.warning("安全报告 GLM 调用失败，降级模板: %s", exc)
        return None, "template"

    @staticmethod
    def _parse_glm_json(text: str) -> Optional[dict]:
        """GLM 可能返回 ```json {…} ``` 包裹的 JSON，做宽松解析。"""
        import json
        import re

        # 取最外层 {…}
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
        for key in ("summary", "risk_highlights", "recommendations"):
            if key not in data:
                return None
        return {k: str(data[k]) for k in ("summary", "risk_highlights", "recommendations")}

    def _template_report(self, facts: dict, coverage: dict) -> dict:
        """AI 不可用时的降级模板——直接拼事实点。"""
        alerts = facts["alert_buckets"]
        risk = facts["risk_buckets"]
        top5 = facts["risk_top5"]

        # 摘要
        if coverage.get("data_degraded"):
            head = "数据可信度降级，结果可能不全。"
        else:
            head = "AI 解读未启用，以下为规则模板输出。"

        alert_part = (
            f"告警 critical {alerts.get('critical', 0)} 条 / high {alerts.get('high', 0)} 条 "
            f"（OpenSearch {'不可用' if alerts.get('_unavailable') else '可用'}）"
        )
        summary = (
            f"{head}"
            f"资产 {facts['asset_total']} 台（在线率 {facts['online_rate']}%）；"
            f"高危资产 {risk.get('critical', 0) + risk.get('high', 0)} 台；"
            f"{alert_part}；"
            f"待处理对账差异 {facts['reconciliation_pending']} 项。"
        )

        # 高亮风险
        risk_lines = []
        for a in top5:
            risk_lines.append(
                f"- {a.get('name', '?')[:24]} ({a.get('ip', '')}) "
                f"风险分 {a.get('risk_score', '?')}"
            )
        if alerts.get("critical", 0) + alerts.get("high", 0) >= 3:
            risk_lines.append(
                f"- 高危告警集中：critical {alerts.get('critical', 0)} / "
                f"high {alerts.get('high', 0)} 条，建议立即排查"
            )
        if facts["reconciliation_pending"]:
            risk_lines.append(
                f"- 台账对账 {facts['reconciliation_pending']} 项未处理"
            )

        # 处置建议（基于规则的兜底）
        rec_lines = []
        if risk.get("critical", 0):
            rec_lines.append("- 优先复盘 critical 风险资产的 `score_breakdown`，定位维度")
        if alerts.get("critical", 0):
            rec_lines.append(f"- 排查 {alerts.get('critical', 0)} 条 critical 告警：按 rule.id 分类")
        if facts["reconciliation_pending"]:
            rec_lines.append(
                f"- 处理 {facts['reconciliation_pending']} 项对账差异（资产对账页 → 逐条确认/忽略）"
            )
        if coverage.get("gaps"):
            rec_lines.append("- 先修复数据源健康问题（见数据健康页），再深入分析")
        if not rec_lines:
            rec_lines.append("- 当前无紧急处置项；继续常规监控")

        return {
            "summary": summary,
            "risk_highlights": "\n".join(risk_lines) if risk_lines else "（无可识别的高亮风险）",
            "recommendations": "\n".join(rec_lines),
            "trigger_meta": None,
        }

    # ---------- 序列化 ----------

    @staticmethod
    def _serialize(r: SecurityReport) -> dict:
        return {
            "id": str(r.id),
            "report_type": r.report_type,
            "period_start": r.period_start.isoformat() if r.period_start else None,
            "period_end": r.period_end.isoformat() if r.period_end else None,
            "title": r.title,
            "summary": r.summary,
            "content": r.content,
            "risk_highlights": r.risk_highlights,
            "recommendations": r.recommendations,
            "data_coverage": r.data_coverage,
            "prompt_version": r.prompt_version,
            "triggered_by": r.triggered_by,
            "trigger_meta": r.trigger_meta,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }