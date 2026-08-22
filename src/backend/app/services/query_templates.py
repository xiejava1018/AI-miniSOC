"""
L2 复合查询模板执行层（PRD F2.1 L2）

【安全边界】本模块是「LLM 之后」的一切。LLM 只负责产出 {template_id, params}；
从进入本模块起，全程 0 次 LLM 调用：
    校验 template_id 在白名单 → 逐参数按 YAML 声明强制类型/范围/枚举
    → 调用写死的 _exec_xxx 实现（纯 SQLAlchemy / 已有 service）

即 LLM 选错模板 = 答非所问（用户可见、可纠正），而不可能变成越权或注入。
所有 SQL 都是参数化的 SQLAlchemy 表达式，没有任何字符串拼接进 SQL。

【数据覆盖率纪律】统计类结果必须带 coverage —— 本项目 73 台资产里 os_name
有 49 台为空，只报「Ubuntu 12 台」会让用户以为全网只有 12 台 Linux。
参见 configs/query_templates.yaml 顶部注释与 compliance_rules.yaml 同款纪律。
"""
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import yaml
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Asset
from app.models.asset_port import AssetPort

logger = logging.getLogger(__name__)

# 模板库路径：项目根 configs/query_templates.yaml（与 compliance.py 同一惯例）
_CONFIG_PATH = Path(__file__).resolve().parents[4] / "configs" / "query_templates.yaml"

MAX_RESULTS = 50

# 分级阈值的权威定义已下沉到 AlertQueryService.LEVEL_*（服务端聚合计数），
# 本模块不再自己分桶，避免项目里再多一个口径变体。
#
# 阈值统一引用中央模块（2026-08-22），本模块不再持有任何口径副本。
# （此前这里的注释还在说“不顺手改 ai_analysis”——那是第一轮修复时的 stale
# 记录，ai_analysis 已在后续统一修复完毕。）
from app.core.alert_levels import LEVEL_CRITICAL, LEVEL_HIGH, LEVEL_MEDIUM, LEVEL_LOW  # noqa: F401

# stats_group_by 允许的维度 → ORM 列（第二层白名单：即使 YAML 被改坏也不会拿到任意列）
_DIMENSION_COLUMNS = {
    "os_name": Asset.os_name,
    "asset_type": Asset.asset_type,
    "criticality": Asset.criticality,
    "exposure_level": Asset.exposure_level,
    "network_segment": Asset.network_segment,
    "business_unit": Asset.business_unit,
    "asset_status": Asset.asset_status,
}


class TemplateError(ValueError):
    """参数校验失败 / 模板不存在。消息直接面向用户，需可读。"""


# ---------------------------------------------------------------- 配置加载

_cache: dict = {}


def load_templates(force: bool = False) -> dict:
    """加载并缓存模板库。文件损坏时抛异常（宁可 L2 整体不可用，也不能带着半个模板库跑）。"""
    if _cache and not force:
        return _cache
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    templates = {t["id"]: t for t in data.get("templates") or []}
    if not templates:
        raise RuntimeError("query_templates.yaml 未定义任何模板")
    _cache.clear()
    _cache.update({
        "version": data.get("templates_version", 0),
        "templates": templates,
        "unsupported_hint": (data.get("unsupported_hint") or "").strip(),
    })
    return _cache


def template_catalog_for_prompt() -> str:
    """把模板库渲染成 Prompt 片段。

    新增模板只改 YAML，Prompt 主逻辑不用动（PRD F2.1 明确要求的扩展性）。
    """
    cfg = load_templates()
    lines = []
    for t in cfg["templates"].values():
        parts = []
        for pname, pspec in (t.get("params") or {}).items():
            flag = "必填" if pspec.get("required") else f"可选,默认{pspec.get('default')}"
            if pspec.get("type") == "enum":
                rng = "|".join(str(c) for c in pspec.get("choices") or [])
            elif pspec.get("type") in ("int", "days"):
                rng = f"{pspec.get('min')}-{pspec.get('max')}"
            else:
                rng = pspec.get("type")
            parts.append(f"{pname}({rng},{flag})")
        line = f"- {t['id']}: {t['description']} 参数: {', '.join(parts) or '无'}"
        if t.get("hints"):
            line += f"\n  提示: {t['hints']}"
        lines.append(line)
    return "\n".join(lines)


def unsupported_hint() -> str:
    try:
        return load_templates()["unsupported_hint"]
    except Exception:
        return "暂时无法处理该问题，请使用资产列表页的筛选器。"


# ---------------------------------------------------------------- 参数校验

def _coerce(pname: str, pspec: dict, raw: Any) -> Any:
    """按 YAML 声明把 LLM 给的值强制成合法值，非法即抛 TemplateError。

    LLM 经常把数字给成字符串（"3389"）或带单位（"7天"），这里做温和纠正；
    但纠正不了的（如枚举越界）一律拒绝，不猜。
    """
    ptype = pspec.get("type")

    if ptype in ("int", "days"):
        if isinstance(raw, bool):  # bool 是 int 子类，先挡掉
            raise TemplateError(f"参数 {pname} 类型错误")
        if isinstance(raw, str):
            digits = "".join(ch for ch in raw if ch.isdigit())
            if not digits:
                raise TemplateError(f"参数 {pname} 需要是数字，收到「{raw}」")
            raw = int(digits)
        if not isinstance(raw, int):
            try:
                raw = int(raw)
            except (TypeError, ValueError):
                raise TemplateError(f"参数 {pname} 需要是数字")
        lo, hi = pspec.get("min"), pspec.get("max")
        if lo is not None and raw < lo:
            raise TemplateError(f"参数 {pname} 不能小于 {lo}（收到 {raw}）")
        if hi is not None and raw > hi:
            raise TemplateError(f"参数 {pname} 不能大于 {hi}（收到 {raw}）")
        return raw

    if ptype == "enum":
        choices = [str(c) for c in pspec.get("choices") or []]
        val = str(raw).strip().lower()
        if val not in choices:
            raise TemplateError(f"参数 {pname} 只支持 {'/'.join(choices)}（收到「{raw}」）")
        return val

    if ptype == "str":
        val = str(raw).strip()
        if not val:
            raise TemplateError(f"参数 {pname} 不能为空")
        maxlen = pspec.get("max_length") or 200
        return val[:maxlen]

    raise TemplateError(f"参数 {pname} 声明了未知类型 {ptype}")


def validate(template_id: str, params: dict) -> tuple[dict, dict]:
    """校验模板与参数，返回 (模板定义, 归一化后的参数)。"""
    cfg = load_templates()
    tpl = cfg["templates"].get(template_id)
    if not tpl:
        raise TemplateError(f"不支持的查询模板：{template_id}")

    raw = params or {}
    clean: dict = {}
    for pname, pspec in (tpl.get("params") or {}).items():
        if pname in raw and raw[pname] is not None and raw[pname] != "":
            clean[pname] = _coerce(pname, pspec, raw[pname])
        elif pspec.get("required"):
            raise TemplateError(f"缺少必填参数 {pname}（{pspec.get('desc') or ''}）")
        elif pspec.get("default") is not None:
            clean[pname] = pspec["default"]
    # LLM 多给的参数直接丢弃，不传进执行器
    return tpl, clean


# ---------------------------------------------------------------- 执行器

def _brief(a: Asset) -> dict:
    return {
        "id": str(a.id),
        "name": a.name,
        "ip": str(a.asset_ip) if a.asset_ip else None,
        "asset_type": a.asset_type,
        "os_name": a.os_name,
        "criticality": a.criticality,
        "asset_status": a.asset_status,
        "risk_score": a.risk_score,
    }


def _exec_port_open(db: Session, p: dict) -> dict:
    """跨表：soc_asset_ports JOIN soc_assets。"""
    port, proto, state = p["port"], p.get("protocol", "tcp"), p.get("state", "open")
    rows = (
        db.query(AssetPort, Asset)
        .outerjoin(Asset, Asset.id == AssetPort.asset_id)
        .filter(AssetPort.port == port, AssetPort.protocol == proto, AssetPort.state == state)
        .order_by(Asset.risk_score.desc().nullslast())
        .limit(MAX_RESULTS)
        .all()
    )
    items = []
    orphan = 0
    for pt, a in rows:
        if a is None:
            # 端口记录存在但资产已删/未关联——如实计数而不是静默丢弃
            orphan += 1
            continue
        item = _brief(a)
        item["port_detail"] = {
            "port": pt.port, "protocol": pt.protocol, "state": pt.state,
            "service": pt.service,
            "scan_time": pt.scan_time.isoformat() if pt.scan_time else None,
        }
        items.append(item)
    total_scanned = db.query(func.count(func.distinct(AssetPort.asset_id))).scalar() or 0
    return {
        "assets": items,
        "total": len(items),
        "notes": [
            f"仅统计已做过端口扫描的资产（当前 {total_scanned} 台有端口数据）；"
            f"未扫描的资产不代表端口未开放。",
        ] + ([f"另有 {orphan} 条端口记录未关联到资产（已排除）。"] if orphan else []),
    }


def _exec_offline_since(db: Session, p: dict) -> dict:
    """时间窗：当前离线 + 离线持续超过 N 天。

    status_updated_at 为空的离线资产无法判定持续时长 → 计入 unknown，
    绝不当成"没超过阈值"而过滤掉（那是把数据缺失伪装成合格）。
    """
    days = p.get("days", 7)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    base = db.query(Asset).filter(Asset.asset_status == "offline")
    offline_total = base.count()

    confirmed = (
        base.filter(Asset.status_updated_at.isnot(None), Asset.status_updated_at < cutoff)
        .order_by(Asset.status_updated_at.asc())
        .limit(MAX_RESULTS)
        .all()
    )
    unknown_cnt = base.filter(Asset.status_updated_at.is_(None)).count()

    items = []
    now = datetime.now(timezone.utc)
    for a in confirmed:
        it = _brief(a)
        su = a.status_updated_at
        it["offline_days"] = round((now - su).total_seconds() / 86400, 1) if su else None
        it["status_updated_at"] = su.isoformat() if su else None
        items.append(it)

    notes = [f"判定依据：asset_status='offline' 且状态更新时间早于 {days} 天前。"]
    if unknown_cnt:
        notes.append(
            f"另有 {unknown_cnt} 台离线资产没有状态更新时间，无法判定离线时长"
            f"（未计入结果，也不代表未超期）。"
        )
    return {
        "assets": items,
        "total": len(items),
        "coverage": {"offline_total": offline_total, "judged": len(items), "unknown": unknown_cnt},
        "notes": notes,
    }


def _exec_asset_recent_alerts(db: Session, p: dict) -> dict:
    """跨源：本地库定位资产 → OpenSearch 查告警。

    OpenSearch 不可达时明确标 degraded，绝不返回空列表让用户误以为"没有告警"。
    """
    key, days = p["asset"], p.get("days", 7)

    q = db.query(Asset)
    # 先按 IP 精确，再按名称模糊（与 F3.1 同样的信号强度分层）
    asset = q.filter(Asset.asset_ip == key).first()
    if asset is None:
        asset = q.filter(Asset.name.ilike(f"%{key}%")).first()
    if asset is None:
        return {
            "assets": [], "total": 0,
            "notes": [f"未找到名称或 IP 匹配「{key}」的资产，请确认资产名或改用 IP。"],
            "alerts": None,
        }

    info = _brief(asset)
    if not asset.asset_ip:
        return {
            "assets": [info], "total": 1, "alerts": None,
            "notes": [f"资产「{asset.name}」没有记录 IP，无法关联告警。"],
        }

    buckets = {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0}
    samples: list = []
    degraded = False
    notes = [f"告警数据来自 OpenSearch（wazuh-alerts-*）服务端聚合计数，回溯 {days} 天。"]
    try:
        from app.services.alert_query import AlertQueryService
        svc = AlertQueryService(db)
        # 必须用聚合：该 IP 可能有数十万条 level-3 噪音，取文档分桶会把
        # critical/high 全部截断成 0（详见 get_level_buckets_by_ip 注释）
        buckets = svc.get_level_buckets_by_ip(str(asset.asset_ip), days=days)
        if buckets.get("critical", 0) or buckets.get("high", 0):
            samples = svc.get_high_severity_samples(str(asset.asset_ip), days=days, limit=5)
    except Exception as e:
        degraded = True
        notes.append(f"OpenSearch 查询失败，告警数据不可用（不代表无告警）：{str(e)[:120]}")
        logger.warning("L2 asset_recent_alerts 告警查询失败: %s", e)
    else:
        notes.append("计数口径：level>=13 critical / >=10 high / >=7 medium / >=4 low；level<4 视为噪音不计入。")

    return {
        "assets": [info],
        "total": 1,
        "alerts": None if degraded else {"buckets": buckets, "high_samples": samples, "days": days},
        "data_degraded": degraded,
        "notes": notes,
    }


def _exec_stats_group_by(db: Session, p: dict) -> dict:
    """分组统计 + 强制数据覆盖率披露。"""
    dim = p["dimension"]
    col = _DIMENSION_COLUMNS.get(dim)
    if col is None:  # 第二层白名单兜底
        raise TemplateError(f"不支持的统计维度：{dim}")

    total = db.query(func.count(Asset.id)).scalar() or 0
    rows = (
        db.query(col, func.count(Asset.id))
        .filter(col.isnot(None))
        .group_by(col)
        .order_by(func.count(Asset.id).desc())
        .all()
    )
    stats = {str(k): c for k, c in rows}
    counted = sum(stats.values())
    missing = total - counted

    notes = [f"共 {total} 台资产，其中 {counted} 台有 {dim} 数据。"]
    if missing:
        pct = round(missing * 100 / total, 1) if total else 0
        notes.append(
            f"⚠️ {missing} 台（{pct}%）该字段为空，未计入分组。"
            f"占比高说明数据采集不全，统计结果不能代表全网实际分布。"
        )
    return {
        "assets": [],
        "stats": stats,
        "stats_dimension": dim,
        "coverage": {"total": total, "counted": counted, "missing": missing},
        "notes": notes,
    }


_EXECUTORS = {
    "port_open": _exec_port_open,
    "offline_since": _exec_offline_since,
    "asset_recent_alerts": _exec_asset_recent_alerts,
    "stats_group_by": _exec_stats_group_by,
}


def execute(db: Session, template_id: str, params: dict) -> dict:
    """校验 + 执行。返回 dict 必含 notes（口径说明），供前端如实展示。"""
    tpl, clean = validate(template_id, params)
    fn = _EXECUTORS.get(template_id)
    if fn is None:
        # YAML 里有但没写实现 —— 属于开发期错误，明确报出来
        raise TemplateError(f"模板 {template_id} 尚未实现执行器")
    out = fn(db, clean)
    out.update({
        "template_id": template_id,
        "template_name": tpl.get("name") or template_id,
        "params": clean,
        "templates_version": load_templates()["version"],
    })
    return out
