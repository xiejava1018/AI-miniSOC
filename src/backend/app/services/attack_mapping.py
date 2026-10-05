"""ATT&CK 映射服务（OH-4.4 · S6）

  - ``sync_from_yaml(db)``：把 configs/attack_patterns.yaml 种子 upsert 进库
    （manual_override 的映射不覆盖）
  - ``map_rule(db, rule_id, rule_groups)``：Wazuh 规则 → 技战术列表
    （精确 id 0.9 优先；组前缀 0.6；未命中返回空——宁缺勿错）
  - ``attack_chain(db, alert_id)``：告警 → 技战术 → 资产 → 业务系统
    （复用 AlertQueryService.get_alert_by_id / _find_asset 与业务系统关联，
    不另建告警-资产锚定）

数据源边界：现网无 ATT&CK STIX feed 通路，技战术目录为离线种子子集；
按需在 YAML 增补后重跑 sync。
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from sqlalchemy.orm import Session

from app.models.attack_pattern import (
    MATCH_RULE_GROUPS,
    MATCH_RULE_ID,
    AlertAttackMapping,
    AttackPattern,
)

logger = logging.getLogger(__name__)

_CONFIG_PATH = (
    Path(__file__).resolve().parents[4] / "configs" / "attack_patterns.yaml"
)

CONF_RULE_ID = 0.9
CONF_RULE_GROUPS = 0.6


def _load_yaml() -> Dict[str, Any]:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"ATT&CK 种子文件缺失：{_CONFIG_PATH}")
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def sync_from_yaml(db: Session) -> Dict[str, int]:
    """种子 upsert：技战术全量 upsert；映射跳过 manual_override。"""
    cfg = _load_yaml()
    techniques = cfg.get("techniques") or []
    mappings = cfg.get("mappings") or []

    patterns_upserted = 0
    for t in techniques:
        tid = str(t.get("technique_id") or "").strip()
        if not tid:
            continue
        row = db.get(AttackPattern, tid)
        if row is None:
            db.add(AttackPattern(
                technique_id=tid,
                name=str(t.get("name") or tid),
                tactic=str(t.get("tactic") or ""),
                url=t.get("url"),
            ))
        else:
            row.name = str(t.get("name") or row.name)
            row.tactic = str(t.get("tactic") or row.tactic)
            row.url = t.get("url") or row.url
        patterns_upserted += 1

    # 先落技战术，再建映射（避免 FK 违反——flush 顺序不保证）
    db.flush()

    known_ids = {str(t.get("technique_id")) for t in techniques}
    mappings_upserted = 0
    for m in mappings:
        tid = str(m.get("technique_id") or "").strip()
        if tid not in known_ids:
            logger.warning("映射引用未定义技战术，跳过：%s", tid)
            continue
        if m.get("rule_id"):
            match_type, value, conf = MATCH_RULE_ID, str(m["rule_id"]), CONF_RULE_ID
        elif m.get("rule_groups"):
            groups = list(m["rule_groups"])
            if not groups:
                continue
            match_type = MATCH_RULE_GROUPS
            value = groups[0]
            conf = CONF_RULE_GROUPS
        else:
            continue

        existing = (
            db.query(AlertAttackMapping)
            .filter(
                AlertAttackMapping.match_type == match_type,
                AlertAttackMapping.match_value == value,
                AlertAttackMapping.technique_id == tid,
            )
            .first()
        )
        if existing is not None:
            if existing.manual_override == "1":
                continue  # 人工修订优先，种子不覆盖
            existing.confidence = conf
        else:
            db.add(AlertAttackMapping(
                technique_id=tid,
                match_type=match_type,
                match_value=value,
                confidence=conf,
                source="seed",
            ))
        mappings_upserted += 1

    db.commit()
    logger.info(
        "ATT&CK 种子同步：techniques=%d mappings=%d",
        patterns_upserted, mappings_upserted,
    )
    return {"patterns": patterns_upserted, "mappings": mappings_upserted}


def map_rule(
    db: Session,
    rule_id: Optional[str],
    rule_groups: Optional[List[str]],
) -> List[Dict[str, Any]]:
    """Wazuh 规则 → 技战术（带目录信息）。未命中返回 []。"""
    if not rule_id and not rule_groups:
        return []

    q = (
        db.query(AlertAttackMapping, AttackPattern)
        .join(AttackPattern,
              AttackPattern.technique_id == AlertAttackMapping.technique_id)
    )

    matched: List[Dict[str, Any]] = []
    seen: set = set()

    # 精确 rule_id 优先
    if rule_id:
        for m, p in (
            q.filter(
                AlertAttackMapping.match_type == MATCH_RULE_ID,
                AlertAttackMapping.match_value == str(rule_id),
            ).all()
        ):
            if p.technique_id not in seen:
                seen.add(p.technique_id)
                matched.append(_pair(m, p))

    # 组前缀匹配：任一 Wazuh 规则组命中映射值即算
    for group in rule_groups or []:
        for m, p in (
            q.filter(
                AlertAttackMapping.match_type == MATCH_RULE_GROUPS,
                AlertAttackMapping.match_value == str(group),
            ).all()
        ):
            if p.technique_id not in seen:
                seen.add(p.technique_id)
                matched.append(_pair(m, p))

    matched.sort(key=lambda x: -x["confidence"])
    return matched


def _pair(m: AlertAttackMapping, p: AttackPattern) -> Dict[str, Any]:
    return {
        "technique_id": p.technique_id,
        "name": p.name,
        "tactic": p.tactic,
        "url": p.url,
        "confidence": m.confidence,
        "match_type": m.match_type,
        "match_value": m.match_value,
    }


def attack_chain(db: Session, alert_id: str) -> Dict[str, Any]:
    """告警 → 技战术 → 资产 → 业务系统。

    告警不存在抛 ValueError。
    """
    from app.services.alert_query import AlertQueryService

    alert_svc = AlertQueryService(db)
    alert = alert_svc.get_alert_by_id(alert_id)
    if not alert:
        raise ValueError(f"告警不存在: {alert_id}")

    rule = alert.get("rule") or {}
    agent = alert.get("agent") or {}
    rule_id = rule.get("id")
    rule_groups = rule.get("groups") or []

    techniques = map_rule(db, rule_id, rule_groups)

    # 资产锚定（复用告警服务既有逻辑）
    linked_asset = alert_svc._find_asset(
        agent_id=agent.get("id"), agent_ip=agent.get("ip"),
    )

    # 资产 → 业务系统
    business_systems: List[Dict[str, Any]] = []
    if linked_asset and linked_asset.get("id"):
        from app.models.business_system import AssetBusiness, BusinessSystem
        rows = (
            db.query(BusinessSystem, AssetBusiness.role)
            .join(AssetBusiness, AssetBusiness.system_id == BusinessSystem.id)
            .filter(AssetBusiness.asset_id == linked_asset["id"])
            .all()
        )
        business_systems = [
            {
                "id": str(bs.id),
                "code": bs.code,
                "name": bs.name,
                "protection_level": bs.protection_level,
                "role": role,
            }
            for bs, role in rows
        ]

    return {
        "alert": {
            "id": alert.get("_id") or alert_id,
            "rule_id": rule_id,
            "rule_description": rule.get("description"),
            "rule_level": rule.get("level"),
            "rule_groups": rule_groups,
            "agent": {"id": agent.get("id"), "name": agent.get("name"),
                      "ip": agent.get("ip")},
            "timestamp": alert.get("@timestamp"),
        },
        "techniques": techniques,
        "linked_asset": linked_asset,
        "business_systems": business_systems,
        "mapped": bool(techniques),
    }
