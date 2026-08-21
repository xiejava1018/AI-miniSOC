"""
智能变更影响分析服务（PRD P3 / F3.1）

职责边界：
  - 用户给出计划变更的自然语言描述（如"升级核心交换机固件"）
  - 服务从描述中提取关键词，定位目标资产，构建粗粒度关联图，
    收集历史告警，把事实拼给 GLM 讲成运维能照做的话
  - 不预测、不编造：PRD §F3.1 v1.2 明确"关系模型建成前，降级为粗粒度评估，
    输出必须标注'基于有限关联数据，未包含拓扑信息'"

数据源：
  - PostgreSQL: soc_assets（定位 + criticality/exposure/risk）+ soc_asset_tags（标签分组）
            + soc_source_health（采集链路状态）+ soc_assets.network_segment（同网段）
            + soc_asset_risk_history（评分趋势）
  - OpenSearch : AlertQueryService.get_alerts_by_ip / get_alert_statistics（告警趋势）

降级路径（与 reconcile_ai 同款）：
  - ai_budget.allow() / GLM Key / 调用失败 → _template_report()
  - 目标资产 0 个 → 模板："未找到匹配资产，描述里需含 IP / 主机名"
  - OpenSearch 不可达 → data_degraded=True + 告警数据为 0
  - data_degraded=True 时 AI 文案开头必须声明
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Asset,
    AssetRiskHistory,
    AssetTag,
    SourceHealth,
)
from app.services.ai_budget import ai_budget
from app.services.alert_query import AlertQueryService

logger = logging.getLogger(__name__)

PROMPT_VERSION = "impact-analysis-v1"
_MAX_RELATED = 15          # 关联资产最多列 15 台，控 token
_LOOKBACK_DAYS = 7         # 历史告警窗口

# 简单的 IP / 主机名 / 中文主机名提取（避免每次都调 GLM 解析）
_IP_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 1) 关键词提取（规则优先 + 必要时的 GLM 兜底）
# ---------------------------------------------------------------------------

def _extract_keywords(description: str) -> dict:
    """从描述里提取 IP / 主机名 / 网段。

    优先用规则（快、零成本）；返回结构化 dict 给后续步骤。
    """
    ips = list(set(_IP_RE.findall(description)))
    # 主机名候选：所有英文主机名/服务名（不要前置限制中文动词，PRD 描述
    # 多样：「k3s-master」「switch-core-01」「prometheus」都该抓到）
    raw_names = re.findall(r"\b([A-Za-z][A-Za-z0-9\-_]{2,40})\b", description)
    # 过滤常见动词/量词（避免错误匹配）
    BLACKLIST = {
        "ssh", "sshd", "tcp", "udp", "api", "app", "vm", "vps", "core",
        "https", "http", "new", "old", "v1", "v2", "v3", "from", "to",
        "via", "and", "the", "for", "with",
    }
    name_hints = [n for n in raw_names if n.lower() not in BLACKLIST]
    # 常见应用/中间件名（弱提示，用于 GLM 上下文）
    common_app_words = re.findall(
        r"\b(prometheus|grafana|kibana|wazuh|loki|nginx|api-gateway|nginx-proxy|mysql|postgres|redis|kafka|rabbitmq|elasticsearch|k3s|kubernetes|docker|etcd|coredns|calico)\b",
        description, re.IGNORECASE,
    )
    # CIDR 优先匹配
    cidr_re = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}0/\d{1,2}\b")
    cidrs = list(set(cidr_re.findall(description)))
    cidr_prefixes = {c.split("/")[0].rsplit(".", 1)[0] + "." for c in cidrs}
    ips = [ip for ip in ips if not any(ip.startswith(p) for p in cidr_prefixes)]
    return {
        "ips": ips,
        "name_hints": name_hints,
        "cidrs": cidrs,
        "weak_hints": list(set([w.lower() for w in common_app_words])),
        "has_any_signal": bool(ips or name_hints or cidrs or common_app_words),
    }
    # 弱提示（不参与资产精确查询，但会写入 facts 上下文）
    weak_hints = list(set(name_hints + [w.lower() for w in common_app_words]))
    return {
        "ips": ips,
        "name_hints": [n for n in name_hints if n.lower() not in {"核心", "备机", "设备"}],
        "cidrs": cidrs,
        "weak_hints": weak_hints,
        "has_any_signal": bool(ips or name_hints or cidrs or common_app_words),
    }


# ---------------------------------------------------------------------------
# 2) 资产定位
# ---------------------------------------------------------------------------

def _locate_assets(db: Session, keywords: dict) -> list[Asset]:
    """按关键词查资产。

    优先级：精确 IP > 名称（含 hint）> 标签值含 hint > 同 CIDR 网段。
    """
    found: dict = {}  # asset.id -> Asset, 避免重复

    # 1. 精确 IP 匹配
    for ip in keywords.get("ips") or []:
        rows = db.query(Asset).filter(Asset.asset_ip == ip).all()
        for a in rows:
            found[str(a.id)] = a

    # 2. 名称 hint 匹配（大小写不敏感）
    for hint in keywords.get("name_hints") or []:
        rows = (
            db.query(Asset)
            .filter(Asset.name.ilike(f"%{hint}%"))
            .limit(5)
            .all()
        )
        for a in rows:
            found[str(a.id)] = a

    # 3. CIDR 匹配（用 LIKE 前缀简化，避免 IPy 依赖）
    for cidr in keywords.get("cidrs") or []:
        prefix = cidr.split("/")[0].rsplit(".", 1)[0] + "."
        rows = (
            db.query(Asset)
            .filter(Asset.asset_ip.like(f"{prefix}%"))
            .limit(10)
            .all()
        )
        for a in rows:
            found[str(a.id)] = a

    return list(found.values())


# ---------------------------------------------------------------------------
# 3) 粗粒度关联图（PRD §F3.1 诚实降级：segment/tags/alerts）
# ---------------------------------------------------------------------------

def _related_assets(db: Session, target: Asset) -> dict:
    """对每个目标资产，返回粗粒度关联：
      - same_segment：同 network_segment
      - shared_tags：任意标签 tag_key+tag_value 相同
    """
    same_segment = []
    if target.network_segment:
        same_segment = (
            db.query(Asset)
            .filter(
                Asset.network_segment == target.network_segment,
                Asset.id != target.id,
            )
            .limit(_MAX_RELATED)
            .all()
        )

    # 拿目标资产的所有 (key, value) 组合
    target_tags = {(t.tag_key, t.tag_value) for t in target.tags or []}
    shared_tags = []
    if target_tags:
        rows = (
            db.query(Asset, AssetTag)
            .join(AssetTag, AssetTag.asset_id == Asset.id)
            .filter(
                Asset.id != target.id,
                AssetTag.tag_key.in_([k for k, _ in target_tags]),
                AssetTag.tag_value.in_([v for _, v in target_tags]),
            )
            .limit(_MAX_RELATED)
            .all()
        )
        seen = set()
        for a, _ in rows:
            if str(a.id) not in seen:
                shared_tags.append(a)
                seen.add(str(a.id))

    return {
        "same_segment": same_segment[:_MAX_RELATED],
        "shared_tags": shared_tags[:_MAX_RELATED],
    }


# ---------------------------------------------------------------------------
# 4) 历史告警 / 源健康 / 风险评分
# ---------------------------------------------------------------------------

def _alert_history(svc: AlertQueryService, ip: str) -> tuple[bool, Optional[str], dict]:
    """返回 (opensearch_ok, error, {critical, high, medium, low, total})"""
    if not ip:
        return True, None, {}
    end = _utcnow()
    start = end - timedelta(days=_LOOKBACK_DAYS)
    try:
        resp = svc.get_alerts_by_ip(ip=ip, limit=1000)
    except httpx.HTTPError as exc:
        return False, f"OpenSearch HTTP 错误: {exc.__class__.__name__}", {}
    except Exception as exc:
        return False, f"OpenSearch 查询失败: {exc.__class__.__name__}: {exc}", {}

    items = resp.get("items") or []
    buckets = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for it in items:
        lv = (it.get("rule") or {}).get("level") or 0
        if lv >= 13: buckets["critical"] += 1
        elif lv >= 10: buckets["high"] += 1
        elif lv >= 7:  buckets["medium"] += 1
        elif lv >= 4:  buckets["low"] += 1
    buckets["total"] = sum(buckets.values())
    return True, None, buckets


def _source_health_summary(db: Session) -> list[dict]:
    rows = db.execute(select(SourceHealth)).scalars().all()
    out = []
    for s in rows:
        overdue = False
        reason = None
        if s.expected_interval_seconds and s.last_success_at:
            age = (_utcnow() - s.last_success_at).total_seconds()
            if age > s.expected_interval_seconds * 3:
                overdue = True
                reason = f"已 {age/3600:.1f}h 无成功（间隔 {s.expected_interval_seconds}s）"
        elif not s.last_success_at:
            overdue = True
            reason = "从未成功采集"
        out.append({
            "source_key": s.source_key,
            "last_success_at": s.last_success_at.isoformat() if s.last_success_at else None,
            "overdue": overdue,
            "reason": reason,
        })
    return out


def _risk_trend(db: Session, asset: Asset, window_days: int = 7) -> dict:
    """最近 window_days 天内的评分变化（取首尾两条评分）。"""
    since = _utcnow() - timedelta(days=window_days)
    rows = (
        db.query(AssetRiskHistory.risk_score, AssetRiskHistory.scored_at)
        .filter(AssetRiskHistory.asset_id == asset.id, AssetRiskHistory.scored_at >= since)
        .order_by(AssetRiskHistory.scored_at.asc())
        .all()
    )
    if len(rows) < 2:
        return {"first": asset.risk_score, "last": asset.risk_score, "delta": 0, "samples": len(rows)}
    return {
        "first": rows[0][0],
        "last": rows[-1][0],
        "delta": rows[-1][0] - rows[0][0],
        "samples": len(rows),
    }


def _serialize_asset(a: Asset) -> dict:
    """资产序列化（模块级，供 analyze / _related_assets 共用）"""
    return {
        "id": str(a.id),
        "name": a.name,
        "ip": a.asset_ip,
        "type": a.asset_type,
        "criticality": a.criticality or "medium",
        "exposure": a.exposure_level or "internal",
        "risk_score": a.risk_score,
        "asset_status": a.asset_status,
        "os_name": a.os_name,
        "tags": [
            {"key": t.tag_key, "value": t.tag_value}
            for t in (a.tags or [])
        ],
        "network_segment": a.network_segment,
    }


# ---------------------------------------------------------------------------
# 主服务
# ---------------------------------------------------------------------------

class ImpactAnalysisService:
    """智能变更影响分析（PRD P3 / F3.1）"""

    def __init__(self, db: Session):
        self.db = db
        self.alert_svc = AlertQueryService(db)

    def analyze(self, change_description: str, change_window_hours: int = 4) -> dict:
        """返回分析结果 dict。参数非法直接 raise ValueError，
        由 API 层转 HTTPException（不在 data 里嵌 code，否则被中间件包成 200套 400）。
        """
        if not change_description or len(change_description.strip()) < 3:
            raise ValueError("change_description 太短（至少 3 字符）")
        if change_window_hours and (change_window_hours < 1 or change_window_hours > 168):
            raise ValueError("change_window_hours 须在 1-168（7天）")

        # 步骤 1: 关键词提取
        keywords = _extract_keywords(change_description)

        # 步骤 2: 定位目标资产
        targets = _locate_assets(self.db, keywords)

        # 预置默认值（避免未匹配分支下 return 里 NameError）
        sources: list = []
        opensearch_ok_all: Optional[bool] = None
        opensearch_errors: list = []

        # 步骤 3-4: 收集事实
        if targets:
            per_target = []
            opensearch_ok_all = True
            for t in targets:
                rel = _related_assets(self.db, t)
                ok, err, alerts = _alert_history(self.alert_svc, t.asset_ip)
                if not ok:
                    opensearch_ok_all = False
                    opensearch_errors.append(err)
                per_target.append({
                    "asset": _serialize_asset(t),
                    "related": {
                        "same_segment": [_serialize_asset(a) for a in rel["same_segment"]],
                        "shared_tags": [_serialize_asset(a) for a in rel["shared_tags"]],
                    },
                    "alert_history_7d": alerts,
                    "risk_trend_7d": _risk_trend(self.db, t),
                })

            sources = _source_health_summary(self.db)
            degraded = (not opensearch_ok_all) or any(s["overdue"] for s in sources)

            # 步骤 5: 拼事实
            facts = self._build_facts(per_target, sources, degraded)

            # 步骤 6: GLM 分析（带降级）
            text, source = self._glm_report(facts, change_description, change_window_hours)
            if text is None:
                text = self._template_report(per_target, sources, degraded, change_window_hours)
                source = "template"
        else:
            # 没找到目标资产，仍返回结构（描述太泛 / 关键词没匹配）
            degraded = False
            facts = {"missing": True, "description": change_description, "keywords": keywords}
            text = {
                "summary": "未在描述中识别到具体资产。建议补充 IP、主机名或子网。",
                "impact": "未识别到目标资产，无法评估。",
                "recommendations": (
                    "请明确写出：1) 操作的具体资产 IP 或主机名；\n"
                    "2) 操作的类型（升级/迁移/重启/下线等）；\n"
                    "3) 计划维护窗口时长。"
                ),
            }
            source = "template"
            per_target = []

        return {
            "change_description": change_description,
            "change_window_hours": change_window_hours,
            "keywords": keywords,
            "targets": [_serialize_asset(a) for a in targets],
            "details": per_target,
            "source_health": sources,
            "data_degraded": degraded,
            "report": text,
            "source": source,            # glm / template
            "prompt_version": PROMPT_VERSION,
            "provenance": {
                "target_count": len(targets),
                "generated_at": _utcnow().isoformat(),
                "opensearch_ok": opensearch_ok_all,
                "opensearch_errors": opensearch_errors or None,
            },
        }

    # ---------- 内部：事实拼装 ----------

    def _build_facts(self, per_target: list, sources: list, degraded: bool) -> dict:
        crit_count = 0
        high_count = 0
        for pt in per_target:
            a = pt["alert_history_7d"]
            crit_count += a.get("critical", 0)
            high_count += a.get("high", 0)
        return {
            "degraded": degraded,
            "targets": per_target,
            "source_health_summary": sources,
            "global_alert_7d": {"critical": crit_count, "high": high_count},
        }

    # ---------- 内部：GLM / 模板 ----------

    def _glm_report(self, facts: dict, description: str, window_hours: int) -> tuple[Optional[dict], str]:
        if not ai_budget.allow():
            return None, "template"
        if not getattr(settings, "GLM_API_KEY", None):
            return None, "template"
        try:
            from zhipuai import ZhipuAI
            facts_str = json_dumps_safe(facts)
            sys_prompt = (
                "你是 AI-miniSOC 变更影响分析助手。基于给定事实生成结构化报告：\n"
                "1) 只使用给定事实，不得推测未提供的信息；\n"
                "2) data_degraded=True 时，summary 必须开头先声明「数据可信度降级，结果可能不全」；\n"
                "3) 按【summary / 影响资产 / 关联业务 / 告警历史 / 风险点 / 维护窗口建议】分节；\n"
                "4) 中文 250-400 字，不用 Markdown 标题（用短横线），可用列表；\n"
                "5) 维护窗口建议要具体（开始/结束/高风险时段）；\n"
                "6) 严格输出 JSON：{\"summary\": \"...\", \"impact\": \"...\", \"recommendations\": \"...\"}"
            )
            user_prompt = (
                f"【变更描述】{description}\n"
                f"【计划维护窗口】{window_hours} 小时\n"
                f"【事实】{facts_str}"
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
            return parsed, "glm"
        except Exception as exc:
            ai_budget.record_failure()
            logger.warning("F3.1 GLM 调用失败，降级模板: %s", exc)
            return None, "template"

    @staticmethod
    def _parse_glm_json(text: str) -> Optional[dict]:
        import json, re
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
        for k in ("summary", "impact", "recommendations"):
            if k not in data:
                return None
        return {k: str(data[k]) for k in ("summary", "impact", "recommendations")}

    def _template_report(self, per_target: list, sources: list, degraded: bool,
                          window_hours: int) -> dict:
        """AI 不可用时直接拼事实——安全稳妥，绝不编造。"""
        if degraded:
            head = "数据可信度降级，结果可能不全（OpenSearch 不可达或数据源过期）。"
        else:
            head = "AI 解读未启用，以下为基于事实拼出的模板分析（未包含拓扑信息）。"

        n_target = len(per_target)
        # 找影响范围最大的资产
        impact_lines = [f"共定位 {n_target} 台目标资产。"]
        for pt in per_target[:5]:
            a = pt["asset"]
            ah = pt["alert_history_7d"]
            related_n = len(pt["related"]["same_segment"]) + len(pt["related"]["shared_tags"])
            impact_lines.append(
                f"- {a['name'][:24]} ({a['ip']}) "
                f"重要度 {a['criticality']} 暴露 {a['exposure']} "
                f"风险分 {a['risk_score'] or '?'}；"
                f"近 7 天告警 critical={ah.get('critical', 0)} high={ah.get('high', 0)}；"
                f"粗粒度关联资产 {related_n} 台"
            )

        rec_lines = []
        crit_high_total = sum(
            pt["alert_history_7d"].get("critical", 0) + pt["alert_history_7d"].get("high", 0)
            for pt in per_target
        )
        if crit_high_total > 0:
            rec_lines.append(
                f"- 高危告警 {crit_high_total} 条，建议选低峰期窗口（夜间 / 周末）避开"
            )
        if any(a["criticality"] == "critical" for pt in per_target for a in [pt["asset"]]):
            rec_lines.append("- 含 critical 资产，建议先备份配置并通知 owner")
        if any(s["overdue"] for s in sources):
            bad = [s["source_key"] for s in sources if s["overdue"]]
            rec_lines.append(f"- 数据源 {', '.join(bad)} 过期，维护期间不要参考其数据")
        if not rec_lines:
            rec_lines.append("- 建议在变更前通知资产 owner / 备份 / 准备回滚预案")

        # 维护窗口建议（粗略规则）
        if crit_high_total > 50 or any(a["criticality"] == "critical" for pt in per_target for a in [pt["asset"]]):
            window_hint = f"建议 {window_hours} 小时窗口起；选 02:00-06:00 低峰；安排双人在场"
        else:
            window_hint = f"可按计划 {window_hours} 小时执行；建议避开业务高峰"

        return {
            "summary": head + f"识别到 {n_target} 台目标资产。",
            "impact": "\n".join(impact_lines),
            "recommendations": "\n".join(rec_lines + [f"- {window_hint}"]),
        }


# ---------------------------------------------------------------------------
# JSON 序列化（处理 datetime/UUID）
# ---------------------------------------------------------------------------

def json_dumps_safe(obj: Any) -> str:
    import json
    from datetime import date, datetime
    def default(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if hasattr(o, "hex") and len(o.hex) == 32:  # UUID
            return str(o)
        if isinstance(o, set):
            return list(o)
        return str(o)
    return json.dumps(obj, ensure_ascii=False, default=default)