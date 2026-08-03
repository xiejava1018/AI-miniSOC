"""
事件服务

将规则引擎的检测结果落地：
  1. 写入 soc_browsing_events
  2. 高风险时升级为 soc_incidents
  3. 通过 NotificationService 推送站内通知 + WebSocket
  4. 抑制期内同 (ip,domain) 不重复生成
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models.browsing_event import BrowsingEvent
from app.models.incident import Incident
from app.models.role import Role
from app.models.user import User
from app.services.browsing_detection.config import DetectionConfig
from app.services.browsing_detection.rule_engine import DetectionFinding
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class EventService:
    """检测结果落地服务"""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.notifier = NotificationService(db)

    async def create_findings(
        self,
        findings: list[DetectionFinding],
        config: DetectionConfig,
    ) -> int:
        """
        批量落地检测结果。返回实际新建的事件数。
        """
        created = 0
        admin_ids = self._resolve_notify_targets(config)

        for finding in findings:
            severity = config.severity_for(finding.score)

            # 抑制检查
            if self._is_suppressed(finding.ip, finding.domain, config.suppress_minutes):
                continue

            # 写检测事件
            event = BrowsingEvent(
                ip=finding.ip,
                domain=finding.domain,
                apptype=finding.apptype or None,
                score=finding.score,
                severity=severity,
                rule_hits=finding.rule_hits,
                source_count=finding.source_count,
                window_start=finding.window_start,
                window_end=finding.window_end,
                status="new",
            )
            self.db.add(event)
            self.db.flush()  # 拿到 event.id

            # 高风险升级为安全事件
            should_notify = severity in ("high", "critical")
            if should_notify:
                incident = self._create_incident(finding, severity)
                if incident:
                    event.incident_id = incident.id
                    await self._notify(finding, severity, admin_ids, event.id, str(incident.id))
            created += 1

        self.db.commit()
        return created

    # ── 升级为 soc_incidents ────────────────────────

    def _create_incident(self, finding: DetectionFinding, severity: str) -> Incident | None:
        """创建安全事件"""
        rule_names = ", ".join(h["rule"] for h in finding.rule_hits)
        details = "\n".join(f"- [{h['rule']}] {h['detail']}" for h in finding.rule_hits)
        description = (
            f"检测到异常上网行为\n\n"
            f"源IP: {finding.ip}\n"
            f"目标: {finding.domain}\n"
            f"分值: {finding.score}\n"
            f"严重等级: {severity}\n"
            f"命中规则: {rule_names}\n"
            f"窗口内记录数: {finding.source_count}\n"
            f"窗口: {finding.window_start:%Y-%m-%d %H:%M} ~ {finding.window_end:%H:%M}\n\n"
            f"规则详情:\n{details}"
        )
        # 截断 domain 避免标题过长
        domain_short = finding.domain[:40] + ("..." if len(finding.domain) > 40 else "")
        incident = Incident(
            title=f"[上网行为] {finding.ip} 异常访问 {domain_short}",
            description=description,
            status="open",
            severity=severity,
            created_by="browsing-detector",
        )
        self.db.add(incident)
        self.db.flush()
        return incident

    # ── 通知 ────────────────────────────────────────

    async def _notify(
        self,
        finding: DetectionFinding,
        severity: str,
        admin_ids: list[int],
        event_id,
        incident_id: str,
    ) -> None:
        rule_names = "/".join(h["rule"] for h in finding.rule_hits)
        title = f"[{severity.upper()}] {finding.ip} 访问 {finding.domain[:30]}"
        content = f"分值 {finding.score}，命中规则 {rule_names}，窗口内 {finding.source_count} 条记录"
        link = f"/#/browsing/event?id={event_id}"
        for uid in admin_ids:
            try:
                await self.notifier.create(
                    user_id=uid,
                    type="alert",
                    title=title,
                    content=content,
                    link=link,
                    push_ws=True,
                )
            except Exception:
                logger.exception("推送通知失败 user_id=%s", uid)

    def _resolve_notify_targets(self, config: DetectionConfig) -> list[int]:
        """解析通知目标用户：配置优先，否则取所有管理员"""
        ids = config.notify_user_id_list
        if ids:
            return ids
        # is_admin 是基于 role.code 的 property，需 join soc_roles 查询
        rows = (
            self.db.query(User.id)
            .join(Role, User.role_id == Role.id)
            .filter(Role.code == "admin")
            .all()
        )
        return [r[0] for r in rows]

    # ── 抑制 ────────────────────────────────────────

    def _is_suppressed(self, ip: str, domain: str, suppress_minutes: int) -> bool:
        """检查 (ip, domain) 是否在抑制期内"""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=suppress_minutes)
        exists = (
            self.db.query(BrowsingEvent.id)
            .filter(
                BrowsingEvent.ip == ip,
                BrowsingEvent.domain == domain,
                BrowsingEvent.created_at >= cutoff,
            )
            .first()
        )
        return exists is not None

    # ── M5: AI 研判（复用 AIAnalysisService）──────────

    async def analyze_event(self, event_id) -> dict:
        """对单个上网行为事件触发 AI 研判

        复用 AIAnalysisService.analyze_alert，将 browsing 上下文映射为告警参数。
        返回 AI 分析结果（explanation / risk_assessment / recommendations）。
        """
        from app.services.ai_analysis import AIAnalysisService

        event = self.db.get(BrowsingEvent, event_id)
        if not event:
            raise ValueError("事件不存在")

        rule_desc = "; ".join(
            f"{h['rule']}({h['weight']}): {h['detail']}" for h in (event.rule_hits or [])
        )
        full_log = (
            f"源IP {event.ip} 访问 {event.domain}，分值 {event.score}({event.severity})，"
            f"窗口内 {event.source_count} 条记录。命中规则: {rule_desc}"
        )

        ai_svc = AIAnalysisService(self.db)
        analysis = await ai_svc.analyze_alert(
            alert_id=str(event.id),
            rule_id=None,
            rule_level=event.score,
            rule_description=f"[上网行为异常] {rule_desc}",
            full_log=full_log,
            agent_name=event.ip,
            agent_ip=event.ip,
        )

        # 关联分析结果到事件
        event.ai_analysis_id = analysis.id
        self.db.commit()

        return {
            "id": str(analysis.id),
            "explanation": analysis.explanation,
            "risk_assessment": analysis.risk_assessment,
            "recommendations": analysis.recommendations,
        }
