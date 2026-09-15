"""
告警 SLA 服务（治本方案 · 2026-09-14）

按业务影响（BIA）维度定义告警响应/解决 SLA：
- core       15 分钟响应 / 4 小时解决
- important  1 小时响应 / 8 小时解决
- normal     4 小时响应 / 24 小时解决
- auxiliary  24 小时响应 / 72 小时解决
- ignorable  72 小时响应 / 7 天解决

SLA 计算流程：
  告警 → agent.ip → soc_assets → business_impact → SLA 配置
  无关联资产时按 normal（SLA 默认值）

设计要点：
- 业务影响（business_impact）不驱动安全评分，仅驱动 SLA / 推送优先级
- data_sensitivity 驱动评分；business_impact 驱动处置——两维度职责清晰
- F4.2 推送场景 7（超 SLA）依赖本服务的 compute_sla_for_alert()
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.core.criticality import BUSINESS_IMPACT_SLA
from app.models import Asset


@dataclass
class SlaState:
    """SLA 状态：响应/解决时长、剩余时间、是否超时"""
    business_impact: str
    business_impact_label: str
    response_minutes: int
    resolve_minutes: int
    response_due_at: Optional[datetime]
    resolve_due_at: Optional[datetime]
    response_remaining_minutes: int    # 负数表示已超时
    resolve_remaining_minutes: int
    response_breached: bool
    resolve_breached: bool

    def to_dict(self) -> dict:
        return {
            "business_impact": self.business_impact,
            "business_impact_label": self.business_impact_label,
            "response_minutes": self.response_minutes,
            "resolve_minutes": self.resolve_minutes,
            "response_due_at": self.response_due_at.isoformat() if self.response_due_at else None,
            "resolve_due_at": self.resolve_due_at.isoformat() if self.resolve_due_at else None,
            "response_remaining_minutes": self.response_remaining_minutes,
            "resolve_remaining_minutes": self.resolve_remaining_minutes,
            "response_breached": self.response_breached,
            "resolve_breached": self.resolve_breached,
        }


class AlertSlaService:
    """告警 SLA 服务"""

    # 业务影响标签（中文）
    BUSINESS_IMPACT_LABELS = {
        "core":       "核心业务",
        "important":  "重要业务",
        "normal":     "一般业务",
        "auxiliary":  "辅助支撑",
        "ignorable":  "可忽略",
    }
    DEFAULT_BUSINESS_IMPACT = "normal"

    def resolve_business_impact(self, db: Session, ip: Optional[str]) -> tuple[str, str]:
        """根据 IP 解析业务影响维度。

        返回 (business_impact_code, business_impact_label)。
        查不到资产时返回默认 normal。
        """
        if not ip:
            return self.DEFAULT_BUSINESS_IMPACT, self.BUSINESS_IMPACT_LABELS[self.DEFAULT_BUSINESS_IMPACT]
        asset = db.query(Asset).filter(Asset.asset_ip == ip).first()
        if not asset:
            return self.DEFAULT_BUSINESS_IMPACT, self.BUSINESS_IMPACT_LABELS[self.DEFAULT_BUSINESS_IMPACT]
        bi = asset.business_impact or self.DEFAULT_BUSINESS_IMPACT
        return bi, self.BUSINESS_IMPACT_LABELS.get(bi, self.BUSINESS_IMPACT_LABELS[self.DEFAULT_BUSINESS_IMPACT])

    def compute_sla_for_alert(
        self,
        db: Session,
        alert_ip: Optional[str],
        alert_time: datetime,
    ) -> SlaState:
        """计算告警 SLA 状态。

        Args:
            db: 数据库会话
            alert_ip: 告警 agent IP
            alert_time: 告警时间（UTC）

        Returns:
            SlaState: SLA 完整状态
        """
        bi_code, bi_label = self.resolve_business_impact(db, alert_ip)
        cfg = BUSINESS_IMPACT_SLA.get(bi_code, BUSINESS_IMPACT_SLA[self.DEFAULT_BUSINESS_IMPACT])
        resp_min = cfg["response_minutes"]
        reso_min = cfg["resolve_minutes"]

        # alert_time 统一 UTC（与现有 alert_query 服务一致）
        if alert_time.tzinfo is None:
            alert_time_utc = alert_time.replace(tzinfo=timezone.utc)
        else:
            alert_time_utc = alert_time.astimezone(timezone.utc)
        now = datetime.now(timezone.utc)

        resp_due = alert_time_utc.timestamp() + resp_min * 60
        reso_due = alert_time_utc.timestamp() + reso_min * 60
        now_ts = now.timestamp()

        resp_remaining = int((resp_due - now_ts) / 60)
        reso_remaining = int((reso_due - now_ts) / 60)

        return SlaState(
            business_impact=bi_code,
            business_impact_label=bi_label,
            response_minutes=resp_min,
            resolve_minutes=reso_min,
            response_due_at=datetime.fromtimestamp(resp_due, tz=timezone.utc),
            resolve_due_at=datetime.fromtimestamp(reso_due, tz=timezone.utc),
            response_remaining_minutes=resp_remaining,
            resolve_remaining_minutes=reso_remaining,
            response_breached=resp_remaining < 0,
            resolve_breached=reso_remaining < 0,
        )

    def check_sla_breach_batch(self, db: Session, alerts: list[dict]) -> list[dict]:
        """批量检查告警 SLA（供 F4.2 推送场景 7 用）。

        Args:
            alerts: 告警 dict 列表，每项需含 agent_ip / timestamp

        Returns:
            新增 sla 字段的告警列表（不修改原 dict）
        """
        enriched = []
        for a in alerts:
            ip = (a.get("agent") or {}).get("ip") or a.get("agent_ip")
            ts = a.get("timestamp") or a.get("@timestamp")
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                except ValueError:
                    ts = datetime.now(timezone.utc)
            elif ts is None:
                ts = datetime.now(timezone.utc)
            sla = self.compute_sla_for_alert(db, ip, ts)
            a2 = dict(a)
            a2["sla"] = sla.to_dict()
            enriched.append(a2)
        return enriched
