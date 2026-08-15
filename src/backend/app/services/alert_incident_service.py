"""
告警→事件转换服务（Phase 3）

把单条告警 / 告警簇一键转为 soc_incidents，并按 IP/agent 关联 soc_asset_incidents。
- build_incident_from_alert(): 单条告警 → 事件（用 rule.level 推导 severity）
- build_incident_from_group(): 告警簇 → 事件（优先用 AI verdict 推导 severity/description；
  无 verdict 时用告警等级启发式）

与 incidents API 的通用 create_incident 不同：本服务面向"告警/簇"自动组装标题/描述/严重度/资产。
告警 API 当前无鉴权（pre-existing），created_by 默认 "system"，可由调用方覆盖。
"""
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Incident, AssetIncident, Asset
from app.services.alert_query import AlertQueryService

logger = logging.getLogger(__name__)

# AI 优先级 P0-P3 → 事件 severity
_PRIORITY_TO_SEVERITY = {"P0": "critical", "P1": "high", "P2": "medium", "P3": "low"}


def _level_to_severity(level) -> str:
    """Wazuh rule.level(1-15) → 事件 severity。"""
    try:
        lv = int(level)
    except (TypeError, ValueError):
        return "medium"
    if lv >= 12:
        return "critical"
    if lv >= 9:
        return "high"
    if lv >= 6:
        return "medium"
    return "low"


def _find_asset_id_by_ip(db: Session, ip: Optional[str]) -> Optional[UUID]:
    if not ip:
        return None
    a = db.query(Asset).filter(Asset.asset_ip == ip).first()
    return a.id if a else None


def _persist_incident(
    db: Session,
    *,
    title: str,
    description: str,
    severity: str,
    created_by: str = "system",
    wazuh_alert_id: Optional[str] = None,
    assigned_to: Optional[str] = None,
    asset_ids: Optional[list] = None,
) -> Incident:
    incident = Incident(
        title=(title or "")[:255],
        description=description,
        status="open",
        severity=severity,
        wazuh_alert_id=wazuh_alert_id,
        assigned_to=assigned_to,
        created_by=created_by or "system",
    )
    db.add(incident)
    db.flush()  # 拿 id
    linked = []
    for aid in asset_ids or []:
        try:
            au = UUID(str(aid))
        except (ValueError, AttributeError, TypeError):
            continue
        db.add(AssetIncident(asset_id=au, incident_id=incident.id))
        linked.append(str(au))
    db.commit()
    db.refresh(incident)
    logger.info(
        "事件已创建: id=%s severity=%s assets=%s title=%s",
        incident.id, incident.severity, len(linked), incident.title,
    )
    return incident


def incident_to_dict(inc: Incident) -> dict:
    return {
        "id": str(inc.id),
        "title": inc.title,
        "description": inc.description,
        "status": inc.status,
        "severity": inc.severity,
        "wazuh_alert_id": inc.wazuh_alert_id,
        "assigned_to": inc.assigned_to,
        "created_by": inc.created_by,
        "created_at": inc.created_at.isoformat() if inc.created_at else None,
    }


def build_incident_from_alert(
    db: Session,
    alert_id: str,
    *,
    created_by: str = "system",
    severity: Optional[str] = None,
    assigned_to: Optional[str] = None,
) -> Incident:
    """从单条告警创建事件。告警不存在抛 ValueError。"""
    svc = AlertQueryService(db)
    alert = svc.get_alert_by_id(alert_id)
    if not alert:
        raise ValueError(f"告警不存在: {alert_id}")

    rule = alert.get("rule") or {}
    agent = alert.get("agent") or {}
    rule_desc = rule.get("description") or f"Wazuh 规则 {rule.get('id')}"
    sev = severity or _level_to_severity(rule.get("level"))
    title = f"[告警] {rule_desc}"

    lines = [
        f"来源告警 ID: {alert.get('_id') or alert_id}",
        f"规则: {rule.get('id')} (level {rule.get('level')}) {rule_desc}",
        f"受影响资产(agent): {agent.get('name')} ({agent.get('ip')})",
    ]
    full_log = alert.get("full_log")
    if full_log:
        lines.append(f"\n原始日志:\n{str(full_log)[:1500]}")
    description = "\n".join(lines)

    asset_id = _find_asset_id_by_ip(db, agent.get("ip"))
    return _persist_incident(
        db,
        title=title,
        description=description,
        severity=sev,
        created_by=created_by,
        assigned_to=assigned_to,
        wazuh_alert_id=str(alert.get("_id") or alert_id),
        asset_ids=[asset_id] if asset_id else None,
    )


def build_incident_from_vulnerability(
    db: Session,
    asset_vulnerability_id,
    *,
    created_by: str = "system",
) -> Incident:
    """从资产-漏洞关联创建事件（T11 / Phase 4.1，2026-08-15）。

    - 标题 = CVE + 资产；severity 由漏洞 severity 直接映射（同构枚举）；
    - 关联机制（§14.5-4）：复用 _persist_incident 现成 asset_ids 走 AssetIncident
      关联 + 描述内嵌 CVE/av_id，零 schema 变更（Incident 表无 asset_vulnerability_id 字段，勿加列）；
    - av 不存在抛 ValueError。
    """
    from app.models.vulnerability import AssetVulnerability, Vulnerability

    av = (
        db.query(AssetVulnerability)
        .filter(AssetVulnerability.id == asset_vulnerability_id)
        .first()
    )
    if not av:
        raise ValueError(f"资产-漏洞关联不存在: {asset_vulnerability_id}")

    vuln = db.query(Vulnerability).filter(Vulnerability.id == av.vulnerability_id).first()
    if not vuln:
        raise ValueError(f"漏洞定义不存在: {av.vulnerability_id}")

    asset = db.query(Asset).filter(Asset.id == av.asset_id).first()
    asset_label = f"{asset.name} ({asset.asset_ip})" if asset else str(av.asset_id)

    vuln_type_label = "配置弱点(SCA)" if vuln.type == "sca" else "CVE漏洞"
    title = f"[漏洞] {vuln.cve_id} @ {asset.name or asset.asset_ip if asset else av.asset_id}"

    lines = [
        f"来源: 脆弱性管理（{vuln_type_label}）",
        f"漏洞: {vuln.cve_id} - {(vuln.title or '')[:120]}",
        f"严重度: {vuln.severity}  CVSS: {vuln.cvss_score if vuln.cvss_score is not None else '未知'}",
        f"在野利用(CISA KEV): {'是' if vuln.has_exploit else '否'}",
        f"受影响资产: {asset_label}",
        f"资产-漏洞关联 ID: {av.id}",
        f"检出时间: {av.detected_at}",
        f"扫描器: {av.scanner}",
    ]
    if vuln.affected_packages:
        pkg = vuln.affected_packages
        lines.append(f"受影响软件包: {pkg.get('name')} {pkg.get('version') or ''}".rstrip())
    if vuln.fix_suggestion:
        lines.append(f"修复建议: {str(vuln.fix_suggestion)[:300]}")
    if av.notes:
        lines.append(f"备注: {str(av.notes)[:300]}")
    description = "\n".join(lines)

    return _persist_incident(
        db,
        title=title,
        description=description,
        severity=str(vuln.severity),
        created_by=created_by,
        asset_ids=[av.asset_id],
    )


def build_incident_from_group(
    db: Session,
    fingerprint: str,
    *,
    hours: int = 24,
    created_by: str = "system",
) -> Incident:
    """从告警簇创建事件。优先用 AI verdict 推导 severity/description；无则告警等级启发式。

    指纹格式非法或簇无数据抛 ValueError。
    """
    svc = AlertQueryService(db)
    detail = svc.get_alert_group_detail(fingerprint, hours=hours, sample_size=3)

    rule_id = detail.get("rule_id")
    rule_desc = detail.get("rule_description") or f"规则 {rule_id}"
    count = detail.get("count")
    level_max = detail.get("level_max")
    agent_name = detail.get("agent_name")
    agent_ip = detail.get("agent_ip")

    # 优先取 AI 簇研判缓存（sync，不触发新的 AI 调用）
    verdict = None
    try:
        from app.services.alert_group_triage_service import AlertGroupTriageService
        verdict = AlertGroupTriageService(db).get_cached_verdict(fingerprint)
    except Exception as e:
        logger.warning("取簇研判缓存失败(fp=%s): %s", fingerprint, e)

    if verdict and verdict.get("priority"):
        sev = _PRIORITY_TO_SEVERITY.get(verdict["priority"], "medium")
    else:
        sev = _level_to_severity(level_max)

    title = f"[告警簇] {rule_desc} ×{count}"
    lines = [
        f"来源告警簇指纹: {fingerprint}",
        f"规则: {rule_id} (level {detail.get('level_min')}-{level_max}) {rule_desc}",
        f"告警数量: {count}",
        f"首末出现: {detail.get('first_seen')} ~ {detail.get('last_seen')}",
        f"受影响资产(agent): {agent_name} ({agent_ip})",
        f"攻击源 IP 数: {detail.get('distinct_srcips') or 0}",
    ]
    if verdict:
        lines += [
            "",
            f"【AI 研判 source={verdict.get('source')}/{verdict.get('model_name')}】",
            f"优先级: {verdict.get('priority')}  置信度: {verdict.get('confidence')}",
            f"理由: {verdict.get('rationale')}",
            f"建议处置: {verdict.get('recommended_action')}",
        ]
    else:
        lines.append("\n（暂无 AI 研判，severity 由告警等级启发式推导）")
    samples = detail.get("samples") or []
    if samples:
        fl = (samples[0] or {}).get("full_log")
        if fl:
            lines += ["", "样本日志:", str(fl)[:1000]]
    description = "\n".join(lines)

    linked = detail.get("linked_asset") or {}
    asset_id = linked.get("asset_id") or _find_asset_id_by_ip(db, agent_ip)
    return _persist_incident(
        db,
        title=title,
        description=description,
        severity=sev,
        created_by=created_by,
        asset_ids=[asset_id] if asset_id else None,
    )
