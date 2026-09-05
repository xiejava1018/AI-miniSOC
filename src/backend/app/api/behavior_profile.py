"""行为画像 API（Phase 2，方案 §9.4 v1.5）

权限（X1 矩阵对齐）：
  - 读（profile/domains/trend/list）：admin + auditor（审计用途）
  - 写（refresh）：admin + operator（require_button_permission，authMark 种在子菜单 permissions）
所有查看行为记入 soc_audit_logs（§6 访问控制）。
注意：HTTP 状态码恒 200，业务错误在 body.code（envelope 中间件）。
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.permissions import require_button_permission, require_role
from app.models.user import User
from app.services.audit_log_service import AuditLogService
from app.services.behavior_profile import service as svc

logger = logging.getLogger(__name__)

router = APIRouter()


def _audit(user: User, action: str, ip: str, detail: str = "") -> None:
    """画像查看/操作留痕（§6）。独立 session，失败不阻断业务。"""
    try:
        AuditLogService(SessionLocal()).create_audit_log(
            user_id=user.id,
            username=user.username,
            action=action,
            resource_type="behavior_profile",
            resource_name=ip,
            new_values={"target": ip, "detail": detail} if detail else {"target": ip},
        )
    except Exception:
        logger.exception("画像审计留痕失败（不阻断）")


@router.get("/behavior-profile/list")
async def get_behavior_profiles(
    traffic_type: Optional[str] = Query(None, pattern="^(human|machine|mixed)$"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    data = svc.get_profiles_summary(db, traffic_type=traffic_type, limit=limit)
    _audit(current_user, "QUERY", "*", f"list traffic_type={traffic_type}")
    return {"total": len(data), "items": data}


@router.get("/behavior-profile/{ip}")
async def get_behavior_profile(
    ip: str,
    days: int = Query(7, ge=1, le=30),
    realtime: int = Query(0, ge=0, le=1,
                          description="1=当日实时（仅限当日口径，不走快照）"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    if realtime:
        try:
            data = svc.compute_realtime(db, ip)
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"实时计算失败: {e}")
        _audit(current_user, "QUERY", ip, "realtime=24h")
        return {"realtime": True, **data}

    data = svc.get_profile(db, ip, days)
    if data is None:
        raise HTTPException(status_code=404, detail=f"该 IP 无画像快照: {ip}")
    _audit(current_user, "QUERY", ip, f"days={days}")
    return data


@router.get("/behavior-profile/{ip}/domains")
async def get_behavior_domains(
    ip: str,
    days: int = Query(7, ge=1, le=30),
    limit: int = Query(50, ge=1, le=200),
    category: Optional[str] = Query(None, max_length=32),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    data = svc.get_domains(db, ip, days, limit=limit, category=category)
    _audit(current_user, "QUERY", ip, f"domains days={days} category={category}")
    return {"ip": ip, "days": days, "total": len(data), "items": data}


@router.get("/behavior-profile/{ip}/trend")
async def get_behavior_trend(
    ip: str,
    days: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    data = svc.get_trend(db, ip, days)
    _audit(current_user, "QUERY", ip, f"trend days={days}")
    return {"ip": ip, "days": days, "items": data}




@router.get("/behavior-profile/{ip}/ai-summary")
async def get_behavior_ai_summary(
    ip: str,
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    """LLM 画像摘要 + 异常解读（GLM 降级走规则模板，source 字段标明）。"""
    profile = svc.get_profile(db, ip, days)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"该 IP 无画像快照: {ip}")
    from app.services.behavior_profile.ai_summary import ProfileAIService
    data = ProfileAIService().summarize(profile)
    _audit(current_user, "QUERY", ip, f"ai-summary days={days} source={data['source']}")
    return data


@router.get("/behavior-profile/{ip}/relations")
async def get_behavior_relations(
    ip: str,
    days: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    """关系画像（层4）：登录出/入站、账号归一化、设备共享度、外部攻击源。"""
    from app.services.behavior_profile.identity import get_relations

    data = get_relations(db, ip, days)
    _audit(current_user, "QUERY", ip, f"relations days={days}")
    return data


@router.get("/behavior-profile/{ip}/risk")
async def get_behavior_risk(
    ip: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    """风险画像（层3）：告警分级/规则榜/漏洞/暴露端口/评分趋势。"""
    data = svc.get_risk(db, ip)
    _audit(current_user, "QUERY", ip, "risk")
    return data


@router.get("/behavior-profile/{ip}/anomalies")
async def get_behavior_anomalies(
    ip: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    """异常判定（层5）：可计算信号子集，只输出信号不定性。"""
    data = svc.get_anomalies(db, ip)
    _audit(current_user, "QUERY", ip, "anomalies")
    return data


@router.get("/behavior-profile/{ip}/domains/{domain}/daily")
async def get_behavior_domain_daily(
    ip: str,
    domain: str,
    days: int = Query(30, ge=1, le=180),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    """单域名逐日访问明细（域名下钻）。"""
    from urllib.parse import unquote

    data = svc.get_domain_daily(db, ip, unquote(domain), days)
    _audit(current_user, "QUERY", ip, f"domain-daily {domain[:50]}")
    return {"ip": ip, "domain": domain, "items": data}


@router.get("/behavior-profile/compare")
async def compare_behavior_profiles(
    a: str = Query(..., max_length=45),
    b: str = Query(..., max_length=45),
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    """双 IP 画像对比（时段/分类余弦相似度，粗粒度参考）。"""
    data = svc.compare_profiles(db, a, b, days)
    _audit(current_user, "QUERY", f"{a}|{b}", f"compare days={days}")
    return data


@router.get("/behavior-profile/{ip}/export")
async def export_behavior_profile(
    ip: str,
    days: int = Query(7, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "auditor")),
):
    """导出画像 HTML 报告（含水印与免责声明）。"""
    from fastapi.responses import HTMLResponse

    profile = svc.get_profile(db, ip, days)
    if profile is None:
        raise HTTPException(status_code=404, detail=f"该 IP 无画像快照: {ip}")
    html = _render_export_html(profile)
    _audit(current_user, "EXPORT", ip, f"days={days}")
    return HTMLResponse(content=html, media_type="text/html",
                        headers={"Content-Disposition":
                                 f'inline; filename="profile-{ip}.html"'})


def _render_export_html(p: dict) -> str:
    """自包含 HTML 报告（无外部依赖；含合规水印）。"""
    import html as _h

    e = _h.escape
    tags = "".join(
        f"<span class='tag' style='border-color:{t.get('color') or '#999'}'>"
        f"<b>{e(t.get('name',''))}</b>"
        f"{' → ' + e(t['alias']) if t.get('alias') else ''}"
        f"<br><small>{e(t.get('evidence',''))}</small></span>"
        for t in (p.get("tags") or [])) or "<p>无标签</p>"
    domains = "".join(
        f"<tr><td>{e(d['domain'])}</td><td>{e(d['category'])}</td>"
        f"<td class='n'>{d['visits']}</td><td class='n'>{d['share']}%</td></tr>"
        for d in (p.get("top_domains") or []))
    hours = "".join(
        f"<div class='hb'><i style='height:{(v / max(max(p.get('by_hour') or [1]) or 1, 1)) * 100:.0f}%'></i>"
        f"<em>{h:02d}</em></div>"
        for h, v in enumerate(p.get("by_hour") or [0] * 24))
    blocks = "".join(
        f"<li>{e(k)}: {v}%</li>" for k, v in (p.get("by_block") or {}).items())
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="utf-8">
<title>行为画像报告 - {e(p['ip'])}</title><style>
body{{font:14px/1.6 -apple-system,'PingFang SC',sans-serif;margin:32px;color:#222}}
h1{{font-size:20px}} .wm{{color:#c92a2a;border:1px solid #ffa8a8;background:#fff0f0;
padding:8px 12px;border-radius:6px;display:inline-block;margin-bottom:16px}}
.tag{{display:inline-block;border:1px solid;border-radius:6px;padding:6px 10px;margin:4px;
font-size:12px}} table{{border-collapse:collapse;width:100%;margin-top:8px}}
th,td{{border:1px solid #dee2e6;padding:6px 10px;text-align:left}}
.n{{text-align:right}} .hb{{display:inline-block;width:14px;height:110px;position:relative;
vertical-align:bottom;margin-right:2px}}
.hb i{{position:absolute;bottom:18px;left:2px;right:2px;background:#1971c2;border-radius:2px 2px 0 0}}
.hb em{{position:absolute;bottom:0;left:0;right:0;font-size:8px;font-style:normal;text-align:center}}
</style></head><body>
<div class="wm">⚠ 本数据仅用于安全审计 · 画像仅输出信号，不定性；结论须经人工复核</div>
<h1>行为画像报告 — {e(p['ip'])}</h1>
<p>主体：{e((p.get('asset') or {{}}).get('name') or '-')} · 窗口 {p.get('days')} 天 ·
访问 {p.get('total'):,} 次 · 流量类型 {e(p.get('traffic_type',''))} ·
置信度 {p.get('confidence')} · 数据缺失 {p.get('gap_days')} 天</p>
<h2>画像标签</h2>{tags}
<h2>24 小时活跃分布</h2><div>{hours}</div>
<h2>时段占比</h2><ul>{blocks}</ul>
<h2>访问域名 TOP</h2><table><tr><th>域名</th><th>分类</th><th>访问量</th><th>占比</th></tr>{domains}</table>
<p style="color:#868e96;font-size:12px">生成时间 {_h.escape(dt.datetime.now(TZ).isoformat(timespec='seconds'))} ·
AI-miniSOC 行为画像 · Loki 窗口外日期显示为数据缺失</p>
</body></html>"""


@router.post("/behavior-profile/{ip}/refresh")
async def refresh_behavior_profile(
    ip: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_button_permission("behavior-profile", "refresh")),
):
    """触发当日实时重算（写操作，admin/operator）。"""
    try:
        data = svc.compute_realtime(db, ip)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"实时重算失败: {e}")
    _audit(current_user, "UPDATE", ip, "refresh(实时重算)")
    return data
