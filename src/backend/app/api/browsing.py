"""
行为检测 API
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_admin
from app.schemas.user import UserResponse as UserResponseSchema
from app.schemas.browsing import (
    BrowsingEventResponse,
    BrowsingEventListResponse,
    BrowsingEventUpdate,
    BrowsingBlacklistCreate,
    BrowsingBlacklistResponse,
    BrowsingBlacklistListResponse,
    BrowsingBaselineResponse,
    BrowsingBaselineListResponse,
    BrowsingStatsResponse,
    BrowsingRuleConfigResponse,
    BrowsingRuleTestRequest,
    BrowsingRuleTestResponse,
)
from app.models.browsing_event import BrowsingEvent
from app.models.browsing_blacklist import BrowsingBlacklist
from app.models.browsing_baseline import BrowsingBaseline
from app.models.system_config import SystemConfig
from app.services.browsing_detection.config import (
    get_detection_config,
    config_cache,
    CONFIG_CATEGORY,
)
from app.services.browsing_detection.loki_client import LokiClient
from app.services.browsing_detection.log_parser import parse_loki_result
from app.services.browsing_detection.rule_engine import RuleEngine
from app.services.browsing_detection.baseline_service import BaselineService

logger = logging.getLogger(__name__)
router = APIRouter()


# ════════════════════════════════════════════════
# 事件
# ════════════════════════════════════════════════

@router.get("/events", response_model=BrowsingEventListResponse)
async def list_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    ip: str | None = None,
    domain: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """异常事件分页列表"""
    q = db.query(BrowsingEvent)
    if ip:
        q = q.filter(BrowsingEvent.ip == ip)
    if domain:
        q = q.filter(BrowsingEvent.domain.ilike(f"%{domain}%"))
    if severity:
        q = q.filter(BrowsingEvent.severity == severity)
    if status:
        q = q.filter(BrowsingEvent.status == status)

    total = q.count()
    items = (
        q.order_by(BrowsingEvent.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return BrowsingEventListResponse(
        items=[BrowsingEventResponse.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size,
    )


@router.get("/events/{event_id}", response_model=BrowsingEventResponse)
async def get_event(
    event_id: str,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """事件详情"""
    event = db.get(BrowsingEvent, _to_uuid(event_id))
    if not event:
        raise HTTPException(status_code=404, detail="事件不存在")
    return BrowsingEventResponse.model_validate(event)


@router.put("/events/{event_id}", response_model=BrowsingEventResponse)
async def update_event(
    event_id: str,
    data: BrowsingEventUpdate,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """更新处置状态"""
    event = db.get(BrowsingEvent, _to_uuid(event_id))
    if not event:
        raise HTTPException(status_code=404, detail="事件不存在")

    if data.status:
        valid = {"new", "confirmed", "false_positive", "resolved", "ignored"}
        if data.status not in valid:
            raise HTTPException(status_code=400, detail=f"无效状态，可选: {valid}")
        event.status = data.status
        if data.status in ("resolved", "ignored", "false_positive") and not event.resolved_at:
            event.resolved_at = datetime.now(timezone.utc)
    if data.resolution_note is not None:
        event.resolution_note = data.resolution_note

    db.commit()
    db.refresh(event)
    return BrowsingEventResponse.model_validate(event)


@router.post("/threat-intel/sync")
async def sync_threat_intel(
    limit: int = Query(5000, ge=100, le=50000),
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """同步威胁情报恶意域名到黑名单（管理员）"""
    from app.services.browsing_detection.threat_intel import ThreatIntelSync
    svc = ThreatIntelSync(db)
    result = svc.sync_urlhaus(limit=limit)
    config_cache.invalidate()
    return result


@router.post("/events/{event_id}/analyze")
async def analyze_event(
    event_id: str,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """AI 研判：对该事件触发 AI 分析"""
    from app.services.browsing_detection.event_service import EventService
    try:
        svc = EventService(db)
        result = await svc.analyze_event(_to_uuid(event_id))
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("AI 研判失败")
        raise HTTPException(status_code=500, detail=f"AI 分析失败: {e}")


@router.post("/events/{event_id}/whitelist")
async def add_to_whitelist(
    event_id: str,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """将该事件的域名加入白名单，并标记为误报"""
    event = db.get(BrowsingEvent, _to_uuid(event_id))
    if not event:
        raise HTTPException(status_code=404, detail="事件不存在")

    # 追加到 whitelist_domains 配置
    cfg = db.query(SystemConfig).filter(
        SystemConfig.category == CONFIG_CATEGORY,
        SystemConfig.key == "whitelist_domains",
    ).first()
    existing = (cfg.value or "") if cfg else ""
    domains = {d.strip() for d in existing.split(",") if d.strip()}
    domains.add(event.domain)
    new_val = ",".join(sorted(domains))
    if cfg:
        cfg.value = new_val
    else:
        db.add(SystemConfig(category=CONFIG_CATEGORY, key="whitelist_domains",
                           value=new_val, value_type="str", description="全局白名单域名"))
    # 标记误报
    event.status = "false_positive"
    event.resolution_note = f"已加入白名单 (by {current_user.username})"
    if not event.resolved_at:
        event.resolved_at = datetime.now(timezone.utc)
    db.commit()

    # 配置缓存失效
    config_cache.invalidate()
    return {"success": True, "message": f"已将 {event.domain} 加入白名单"}


# ════════════════════════════════════════════════
# 黑名单
# ════════════════════════════════════════════════

@router.get("/blacklist", response_model=BrowsingBlacklistListResponse)
async def list_blacklist(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    domain: str | None = None,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """黑名单列表（分页）"""
    q = db.query(BrowsingBlacklist)
    if domain:
        q = q.filter(BrowsingBlacklist.domain.ilike(f"%{domain}%"))
    total = q.count()
    items = (
        q.order_by(BrowsingBlacklist.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return BrowsingBlacklistListResponse(items=items, total=total)


@router.post("/blacklist", response_model=BrowsingBlacklistResponse, status_code=201)
async def create_blacklist(
    data: BrowsingBlacklistCreate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """添加黑名单域名（管理员）"""
    domain = data.domain.strip().lower()
    exists = db.query(BrowsingBlacklist).filter(BrowsingBlacklist.domain == domain).first()
    if exists:
        raise HTTPException(status_code=400, detail="该域名已存在")
    item = BrowsingBlacklist(
        domain=domain, source=data.source, reason=data.reason, created_by=current_user.id,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    config_cache.invalidate()
    return BrowsingBlacklistResponse.model_validate(item)


@router.delete("/blacklist/{blacklist_id}")
async def delete_blacklist(
    blacklist_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """删除黑名单域名（管理员）"""
    item = db.get(BrowsingBlacklist, blacklist_id)
    if not item:
        raise HTTPException(status_code=404, detail="黑名单记录不存在")
    db.delete(item)
    db.commit()
    config_cache.invalidate()
    return {"success": True, "message": "已删除"}


# ════════════════════════════════════════════════
# 基线
# ════════════════════════════════════════════════

@router.get("/baseline", response_model=BrowsingBaselineListResponse)
async def list_baseline(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    ip: str | None = None,
    domain: str | None = None,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """基线列表"""
    q = db.query(BrowsingBaseline)
    if ip:
        q = q.filter(BrowsingBaseline.ip == ip)
    if domain:
        q = q.filter(BrowsingBaseline.domain.ilike(f"%{domain}%"))
    total = q.count()
    items = (
        q.order_by(BrowsingBaseline.last_seen.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return BrowsingBaselineListResponse(
        items=[BrowsingBaselineResponse.model_validate(i) for i in items],
        total=total, page=page, page_size=page_size,
    )


# ════════════════════════════════════════════════
# 统计
# ════════════════════════════════════════════════

@router.get("/stats", response_model=BrowsingStatsResponse)
async def get_stats(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """统计：今日异常数、等级分布、规则分布、IP 分布"""
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    q = db.query(BrowsingEvent).filter(BrowsingEvent.created_at >= today_start)
    today_total = q.count()

    # 等级分布
    sev_rows = db.query(BrowsingEvent.severity, func.count()).filter(
        BrowsingEvent.created_at >= today_start
    ).group_by(BrowsingEvent.severity).all()
    today_by_severity = {r[0]: r[1] for r in sev_rows}

    # 规则分布 + IP 分布需解析 rule_hits JSONB
    today_events = q.order_by(BrowsingEvent.created_at.desc()).limit(500).all()
    rule_counter: dict[str, int] = {}
    ip_counter: dict[str, int] = {}
    for e in today_events:
        for h in (e.rule_hits or []):
            rule = h.get("rule", "?") if isinstance(h, dict) else "?"
            rule_counter[rule] = rule_counter.get(rule, 0) + 1
        ip_counter[e.ip] = ip_counter.get(e.ip, 0) + 1

    today_by_ip = sorted(
        [{"ip": k, "count": v} for k, v in ip_counter.items()],
        key=lambda x: x["count"], reverse=True,
    )[:10]

    return BrowsingStatsResponse(
        today_total=today_total,
        today_by_severity=today_by_severity,
        today_by_rule=rule_counter,
        today_by_ip=today_by_ip,
    )


# ════════════════════════════════════════════════
# 规则配置 & 试运行
# ════════════════════════════════════════════════

@router.get("/rules/config", response_model=BrowsingRuleConfigResponse)
async def get_rules_config(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """读取规则配置"""
    rows = db.query(SystemConfig).filter(
        SystemConfig.category == CONFIG_CATEGORY
    ).order_by(SystemConfig.key).all()
    return BrowsingRuleConfigResponse(configs=[
        {"id": r.id, "key": r.key, "value": r.value, "value_type": r.value_type, "description": r.description}
        for r in rows
    ])


@router.put("/rules/config")
async def update_rules_config(
    configs: dict,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """批量更新规则配置（管理员）。body: {key: value, ...}"""
    updated = 0
    for key, value in configs.items():
        row = db.query(SystemConfig).filter(
            SystemConfig.category == CONFIG_CATEGORY,
            SystemConfig.key == key,
        ).first()
        if row:
            row.value = str(value)
            updated += 1
    db.commit()
    config_cache.invalidate()
    return {"success": True, "updated": updated}


@router.post("/rules/test", response_model=BrowsingRuleTestResponse)
async def test_rules(
    data: BrowsingRuleTestRequest,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """规则试运行：回放最近 N 分钟，返回检测结果（不入库、不通知）"""
    config = get_detection_config(db)
    end = datetime.now(timezone.utc)
    start = end - timedelta(minutes=data.minutes)
    start_ns = int(start.timestamp() * 1_000_000_000)
    end_ns = int(end.timestamp() * 1_000_000_000)

    client = LokiClient()
    try:
        streams = client.query_range('{exporter="OTLP"}', start_ns, end_ns, limit=10000)
    finally:
        client.close()

    records = parse_loki_result(streams)
    baseline = BaselineService(db)
    internal_ips = {r.ip for r in records if r.is_internal}
    known_map = baseline.get_known_domains_bulk(internal_ips)
    engine = RuleEngine(db, config)
    findings = engine.evaluate(records, known_map, start, end)

    return BrowsingRuleTestResponse(
        findings=[
            {
                "ip": f.ip, "domain": f.domain, "apptype": f.apptype,
                "score": f.score, "severity": config.severity_for(f.score),
                "rule_hits": f.rule_hits, "source_count": f.source_count,
            }
            for f in findings
        ],
        stats={
            "fetched": sum(len(s.get("values", [])) for s in streams),
            "parsed": len(records),
            "findings": len(findings),
        },
    )


def _to_uuid(event_id: str):
    try:
        from uuid import UUID
        return UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的ID格式")
