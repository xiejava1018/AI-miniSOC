"""
行为检测 API
"""

import json
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


from datetime import datetime, timedelta, timezone

# 中国时区（北京时间 UTC+8），用于展示
_CST = timezone(timedelta(hours=8))


def _fmt_cst(dt: datetime) -> str:
    """转北京时间(UTC+8)格式化展示，与路由器日志本地时间一致"""
    return dt.astimezone(_CST).strftime("%Y-%m-%d %H:%M:%S")


def _extract_body(line: str) -> str:
    """从 Loki 的 {\"body\":\"...\"} JSON 行提取 body 字段"""
    body = line.strip()
    if body.startswith("{"):
        try:
            obj = json.loads(body)
            if isinstance(obj, dict) and "body" in obj:
                return obj["body"]
        except (json.JSONDecodeError, TypeError):
            pass
    return body


def _parse_iso(s: str | None):
    """解析 ISO 时间字符串为带时区 datetime"""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


@router.get("/logs")
async def query_logs(
    ip: str | None = None,
    domain: str | None = None,
    apptype: str | None = None,
    keyword: str | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(200, ge=1, le=10000),
    current_user: UserResponseSchema = Depends(get_current_user),
):
    """查询原始行为日志（多条件，从 Loki 实时查询）"""
    import asyncio
    from app.services.browsing_detection.log_parser import _RE_DOMAIN, _RE_APPTYPE

    now = datetime.now(timezone.utc)
    end_dt = _parse_iso(end) or now
    start_dt = _parse_iso(start) or (now - timedelta(hours=1))
    start_ns = int(start_dt.timestamp() * 1_000_000_000)
    end_ns = int(end_dt.timestamp() * 1_000_000_000)

    # 构造 LogQL
    selector = f'{{exporter="OTLP", ip="{ip}"}}' if ip else '{exporter="OTLP"}'
    query = selector
    if domain:
        query += f' |= "{domain}"'
    if apptype:
        query += f' |= "apptype:{apptype}"'
    if keyword:
        query += f' |= "{keyword}"'

    client = LokiClient()
    try:
        streams = await asyncio.to_thread(client.query_range, query, start_ns, end_ns, limit)
    finally:
        client.close()

    logs = []
    for stream in streams:
        stream_ip = (stream.get("stream") or {}).get("ip", "")
        for ts_ns, line in (stream.get("values") or []):
            body = _extract_body(line)
            ts = datetime.fromtimestamp(int(ts_ns) / 1_000_000_000, tz=timezone.utc)
            m_d = _RE_DOMAIN.search(body)
            m_a = _RE_APPTYPE.search(body)
            logs.append({
                "ts": _fmt_cst(ts),
                "ip": stream_ip,
                "domain": (m_d.group(1).rstrip(".") if m_d else ""),
                "apptype": (m_a.group(1) if m_a else ""),
                "action": "url" if m_d else ("app" if m_a else ""),
                "body": body,
            })
    logs.sort(key=lambda x: x["ts"], reverse=True)
    return {"total": len(logs), "logs": logs, "query": query}


def _to_uuid(event_id: str):
    try:
        from uuid import UUID
        return UUID(event_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的ID格式")


@router.get("/statistics")
async def get_browsing_statistics(
    hours: int = Query(24, ge=1, le=168),
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """行为统计概览：多维度聚合统计（从 Loki 实时聚合，不受10000条限制）"""
    import asyncio
    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=hours)
    start_ns = int(start.timestamp() * 1_000_000_000)
    end_ns = int(now.timestamp() * 1_000_000_000)
    rng = f"[{hours}h]"

    async def run_instant(q: str):
        client = LokiClient()
        try:
            return await asyncio.to_thread(client.query, q, end_ns)
        except Exception:
            logger.exception("聚合查询失败: %s", q)
            return []
        finally:
            client.close()

    async def run_range(q: str, step: str):
        client = LokiClient()
        try:
            return await asyncio.to_thread(client.query_range, q, start_ns, end_ns, 10000, "forward", step)
        except Exception:
            logger.exception("范围聚合失败: %s", q)
            return []
        finally:
            client.close()

    # 并发查询多个维度
    ip_q = f'sum by (ip) (count_over_time({{exporter="OTLP"}}{rng}))'
    domain_q = f'sum by (domain) (count_over_time({{exporter="OTLP"}} |= "网址" | regexp "网址:(?P<domain>[^ ]+)"{rng}))'
    apptype_q = f'sum by (apptype) (count_over_time({{exporter="OTLP"}} |= "apptype" | regexp "apptype:(?P<apptype>[^ ]+)"{rng}))'
    tunnel_q = f'sum(count_over_time({{exporter="OTLP"}} |~ "easytier|stun|frp|zerotier|tailscale|n2n|wireguard"{rng}))'
    trend_q = 'sum(count_over_time({exporter="OTLP"}[1h]))'
    # 热力图 & 凌晨活跃：固定查最近7天（多天×24小时）
    hm_start = now - timedelta(days=2)
    hm_start_ns = int(hm_start.timestamp() * 1_000_000_000)
    heatmap_q = 'sum(count_over_time({exporter="OTLP"}[1h]))'
    night_q = 'sum by (ip) (count_over_time({exporter="OTLP"}[1h]))'

    async def run_range_7d(q: str, step: str):
        client = LokiClient()
        try:
            return await asyncio.to_thread(client.query_range, q, hm_start_ns, end_ns, 200, "forward", step)
        except Exception:
            logger.exception("7d聚合失败: %s", q)
            return []
        finally:
            client.close()

    ip_r, domain_r, apptype_r, tunnel_r, trend_r, heatmap_r, night_r = await asyncio.gather(
        run_instant(ip_q),
        run_instant(domain_q),
        run_instant(apptype_q),
        run_instant(tunnel_q),
        run_range(trend_q, "3600"),
        run_range_7d(heatmap_q, "3600"),
        run_range_7d(night_q, "3600"),
    )

    # 解析瞬时 vector [{metric, value:[ts, val]}]
    def vec_top(r, label, n=10):
        rows = [(x.get("metric", {}).get(label, "?"), int(float(x.get("value", [0, 0])[1]))) for x in r]
        rows.sort(key=lambda x: -x[1])
        return [{"key": k, "count": v} for k, v in rows[:n]], len(rows)

    top_ips, ip_count = vec_top(ip_r, "ip")
    top_domains, domain_count = vec_top(domain_r, "domain")
    apptype_rows = [(x.get("metric", {}).get("apptype", "?"), int(float(x.get("value", [0, 0])[1]))) for x in apptype_r]
    apptype_rows.sort(key=lambda x: -x[1])
    apptype_dist = [{"name": k, "value": v} for k, v in apptype_rows]
    tunnel_count = int(float(tunnel_r[0].get("value", [0, 0])[1])) if tunnel_r else 0

    # 趋势解析（转北京时间）
    trend = []
    if trend_r:
        for ts, val in trend_r[0].get("values", []):
            t = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(_CST)
            trend.append({"ts": t.strftime("%m-%d %H:00"), "count": int(float(val))})
    total = sum(p["count"] for p in trend)

    # 异常事件数（DB，窗口内）
    event_count = db.query(BrowsingEvent).filter(BrowsingEvent.created_at >= start).count()

    # 24h 时段热力图（7天 × 24小时）
    dates_list, date_idx = [], {}
    heat_data = []
    if heatmap_r:
        for ts, val in heatmap_r[0].get("values", []):
            t = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(_CST)
            ds = t.strftime("%m-%d")
            if ds not in date_idx:
                date_idx[ds] = len(dates_list)
                dates_list.append(ds)
            heat_data.append([t.hour, date_idx[ds], int(float(val))])

    # 凌晨活跃 IP（北京时间 2-5 点，最近7天）
    night_counter = {}
    for series in night_r:
        ip = series.get("metric", {}).get("ip", "?")
        for ts, val in series.get("values", []):
            t = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(_CST)
            if 2 <= t.hour < 5:
                night_counter[ip] = night_counter.get(ip, 0) + int(float(val))
    night_ips = sorted(
        [{"ip": k, "count": v} for k, v in night_counter.items()],
        key=lambda x: -x["count"],
    )[:10]

    return {
        "hours": hours,
        "summary": {
            "total": total, "ip_count": ip_count, "domain_count": domain_count,
            "event_count": event_count, "tunnel_count": tunnel_count,
        },
        "trend": trend,
        "top_ips": top_ips,
        "top_domains": top_domains,
        "apptype_dist": apptype_dist,
        "heatmap": {"dates": dates_list, "hours": list(range(24)), "data": heat_data},
        "night_ips": night_ips,
    }


@router.get("/events/{event_id}/logs")
async def get_event_logs(
    event_id: str,
    limit: int = Query(100, ge=1, le=500),
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取事件对应的原始 Loki 日志（按 ip + 域名 + 检测窗口查询）"""
    import asyncio

    event = db.get(BrowsingEvent, _to_uuid(event_id))
    if not event:
        raise HTTPException(status_code=404, detail="事件不存在")

    # 时间窗口前后各扩 1 分钟，确保覆盖原始日志
    start = event.window_start - timedelta(minutes=1)
    end = event.window_end + timedelta(minutes=1)
    start_ns = int(start.timestamp() * 1_000_000_000)
    end_ns = int(end.timestamp() * 1_000_000_000)

    # 构造 LogQL：按 ip 标签 + 域名/apptype 关键字过滤
    domain = event.domain or ""
    if domain.startswith("[app]"):
        keyword = event.apptype or ""
    else:
        keyword = domain
    if keyword:
        query = f'{{exporter="OTLP", ip="{event.ip}"}} |= "{keyword}"'
    else:
        query = f'{{exporter="OTLP", ip="{event.ip}"}}'

    client = LokiClient()
    try:
        streams = await asyncio.to_thread(
            client.query_range, query, start_ns, end_ns, limit
        )
    finally:
        client.close()

    # 提取日志行
    logs = []
    for stream in streams:
        for ts_ns, line in (stream.get("values") or []):
            body = _extract_body(line)
            ts = datetime.fromtimestamp(int(ts_ns) / 1_000_000_000, tz=timezone.utc)
            logs.append({"ts": _fmt_cst(ts), "body": body})
    logs.sort(key=lambda x: x["ts"])
    return {"total": len(logs), "logs": logs, "query": query}
