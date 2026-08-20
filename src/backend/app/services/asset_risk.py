"""
资产风险评分服务（PRD F1.1 / v1.2.1，P3 MVP）

设计要点（对应 PRD 条款）：
- 规则引擎计算评分本体（不调 GLM）；规则外置 soc_system_config(category='risk_rules')，
  支持运行时调整（PUT /assets/risk/rules），带 60s 缓存（对齐 alert_governance_config 模式）
- 四维度：暴露面 30% / 系统健康度 25% / 告警密度 25% / 资产重要性 20%（权重可配）
- 可解释性（§八-C）：每次评分落 score_breakdown —— 维度分/权重/命中理由/输入数据
- 数据稀疏降级（§4.5）：维度缺失按 50% 权重计入并重归一化，breakdown 标 data_gap；
  四维全缺 → 返回 None（前端显示 N/A，不误导为"0 分很安全"）
- 系统健康度消费漏洞级评分输出（VulnerabilityAIService，PRD v1.2.1「关系」节），
  口径共享 exposure_level / criticality，本服务不改动 VulnerabilityAIService
- GLM 摘要（AI 增强）：仅 score>=60 或 7 天内上升>=20 的资产触发；24h 缓存；
  走 ai_budget 限流；GLM 不可用 → 规则化模板文案降级（§八-C 降级表）
"""
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Asset, AlertGroupAnalysis
from app.models.asset_risk import AssetRiskHistory
from app.models.system_config import SystemConfig
from app.services.ai_budget import ai_budget

logger = logging.getLogger(__name__)

RULES_CATEGORY = "risk_rules"
RULES_KEY = "rules"
_CACHE_TTL = 60  # 秒

# ---------------------------------------------------------------------------
# 默认规则（PRD F1.1 risk_rules.yaml 的 DB 等价物；覆盖存 soc_system_config）
# ---------------------------------------------------------------------------

DEFAULT_RULES: dict = {
    "weights": {"exposure": 0.30, "health": 0.25, "alerts": 0.25, "importance": 0.20},
    "exposure": {
        "high_risk_ports": [22, 23, 135, 139, 445, 3389, 5900, 6379, 27017],
        "per_port_score": 25,           # 每个开放高危端口加分，4 个即满
        "cap": 100,
        "public_exposure_bonus": 20,    # exposure_level == public 追加（封顶不变）
    },
    "health": {
        # 漏洞维度（主路径）：消费 VulnerabilityAIService 口径（PRD v1.2.1 关系节）
        "from_vulnerabilities": {
            "max_vuln_score_weight": 0.6,   # 活跃漏洞最高风险分 × 0.6
            "critical": 30,                 # 每个活跃 critical 漏洞加分
            "high": 15,
            "medium": 5,
            "count_bonus_cap": 40,          # 数量加分封顶（合计占 0.4）
        },
        # 预置 EOL 判断（F3.2 将升级为独立 EOL 参考表，此处为兜底子集）
        "eol_systems": {
            "centos 7": "2024-06-30",
            "centos 8": "2021-12-31",
            "ubuntu 16.04": "2021-04-30",
            "ubuntu 18.04": "2023-05-31",
            "windows 7": "2020-01-14",
            "windows server 2008": "2020-01-14",
            "windows server 2012": "2023-10-10",
        },
        "eol_score": 100,
    },
    "alerts": {
        "window_days": 7,
        "priority_scores": {"P0": 20, "P1": 20, "P2": 8, "P3": 2},
        "cap": 100,
    },
    "importance": {
        "criticality": {"critical": 100, "high": 70, "medium": 40, "low": 20},
        "data_classification_bonus": {"secret": 15, "confidential": 10, "internal": 0, "public": 0},
    },
    "summary": {
        "min_score": 60,          # 只有 score>=60 才生成 GLM 摘要
        "cache_hours": 24,
        "rise_threshold": 20,     # 7 天内上升 >=20 分也触发
        "rise_window_days": 7,
        "per_run_cap": 20,        # 单次批跑最多生成 N 条 GLM 摘要（控时延）
    },
}

_rules_cache = {"value": None, "at": 0.0}
_cache_lock = threading.Lock()


def _deep_merge(base: dict, override: dict) -> dict:
    """浅层维度合并：override 里的键覆盖 base，递归 dict。"""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 服务主体
# ---------------------------------------------------------------------------

class AssetRiskService:
    """资产风险评分：规则引擎 + 历史落库 + GLM 摘要（预算限流）"""

    def __init__(self, db: Session):
        self.db = db

    # ---------- 规则存取 ----------

    def load_rules(self, force: bool = False) -> dict:
        now = time.time()
        with _cache_lock:
            if not force and _rules_cache["value"] is not None and (now - _rules_cache["at"]) < _CACHE_TTL:
                return _rules_cache["value"]
        rules = DEFAULT_RULES
        try:
            row = (
                self.db.query(SystemConfig)
                .filter(SystemConfig.category == RULES_CATEGORY, SystemConfig.key == RULES_KEY)
                .first()
            )
            if row and row.value:
                rules = _deep_merge(DEFAULT_RULES, json.loads(row.value))
        except Exception as e:
            logger.warning("读取 risk_rules 配置失败，用默认规则: %s", e)
        with _cache_lock:
            _rules_cache["value"] = rules
            _rules_cache["at"] = now
        return rules

    def save_rules(self, override: dict, user_id: Optional[int] = None) -> dict:
        """校验并保存规则覆盖；权重和必须接近 1。返回合并后的完整规则。"""
        merged = _deep_merge(DEFAULT_RULES, override or {})
        weights = merged.get("weights", {})
        total_w = sum(float(weights.get(k, 0)) for k in ("exposure", "health", "alerts", "importance"))
        if abs(total_w - 1.0) > 0.01:
            raise ValueError(f"四维度权重之和须为 1.0（当前 {total_w:.2f}）")
        row = (
            self.db.query(SystemConfig)
            .filter(SystemConfig.category == RULES_CATEGORY, SystemConfig.key == RULES_KEY)
            .first()
        )
        payload = json.dumps(override, ensure_ascii=False)
        if row:
            row.value = payload
            if user_id is not None:
                row.updated_by = user_id
        else:
            self.db.add(SystemConfig(
                category=RULES_CATEGORY, key=RULES_KEY, value=payload,
                value_type="json", description="资产风险评分规则覆盖（与内置默认深合并）",
                updated_by=user_id,
            ))
        self.db.commit()
        with _cache_lock:  # 失效缓存
            _rules_cache["value"] = None
            _rules_cache["at"] = 0.0
        return merged

    # ---------- 维度评分 ----------

    def _score_exposure(self, asset: Asset, rules: dict) -> dict:
        cfg = rules["exposure"]
        ports = list(getattr(asset, "ports", []) or [])
        open_ports = [p for p in ports if (p.state or "open") == "open"]
        hit = sorted({p.port for p in open_ports if p.port in set(cfg["high_risk_ports"])})
        reasons, score = [], 0
        if hit:
            score = min(cfg["cap"], len(hit) * cfg["per_port_score"])
            reasons.append(f"开放高危端口 {len(hit)} 个: {', '.join(str(x) for x in hit)}")
        else:
            reasons.append("未发现开放的高危端口")
        if (asset.exposure_level or "internal") == "public":
            score = min(cfg["cap"], score + cfg["public_exposure_bonus"])
            reasons.append("公网可达（exposure_level=public）")
        # 无任何端口记录 → 数据缺失（半权），只有公网标记仍计分
        data_gap = len(ports) == 0
        if data_gap:
            reasons.append("无端口扫描数据（维度按 50% 权重计入）")
        return {"score": score, "data_gap": data_gap, "reasons": reasons,
                "inputs": {"open_high_risk_ports": hit, "port_records": len(ports)}}

    def _score_health(self, asset: Asset, rules: dict) -> dict:
        """主路径：活跃漏洞（VulnerabilityAIService 口径）；无扫描数据回退 OS EOL 判断。"""
        from app.models.vulnerability import AssetVulnerability, Vulnerability
        from app.services.vulnerability_ai import VulnerabilityAIService

        cfg = rules["health"]["from_vulnerabilities"]
        rows = (
            self.db.query(AssetVulnerability, Vulnerability)
            .join(Vulnerability, AssetVulnerability.vulnerability_id == Vulnerability.id)
            .filter(AssetVulnerability.asset_id == asset.id)
            .all()
        )
        open_rows = [(av, v) for av, v in rows if av.status != "fixed"]

        if rows:  # 有扫描覆盖（无论是否已修复）
            counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            max_vuln = 0.0
            for _, v in open_rows:
                sev = (v.severity or "low").lower()
                if sev in counts:
                    counts[sev] += 1
                try:
                    s = VulnerabilityAIService.calculate_risk_score(
                        cvss_score=float(v.cvss_score or 0.0),
                        asset_criticality=asset.criticality or "medium",
                        exposure_level=asset.exposure_level or "internal",
                        has_exploit=bool(v.has_exploit),
                    )
                    max_vuln = max(max_vuln, s)
                except Exception:
                    pass
            count_bonus = min(
                cfg["count_bonus_cap"],
                counts["critical"] * cfg["critical"] + counts["high"] * cfg["high"] + counts["medium"] * cfg["medium"],
            )
            score = min(100, round(max_vuln * cfg["max_vuln_score_weight"] + count_bonus))
            reasons = [f"活跃漏洞: critical {counts['critical']} / high {counts['high']} / medium {counts['medium']}"]
            if max_vuln:
                reasons.append(f"最高漏洞风险分 {max_vuln:.0f}（VulnerabilityAIService 口径）")
            if not open_rows:
                reasons.append("已扫描，无未修复漏洞")
            return {"score": score, "data_gap": False, "reasons": reasons,
                    "inputs": {"open_vuln_counts": counts, "max_vuln_score": round(max_vuln, 2)}}

        # 无漏洞扫描数据 → OS EOL 兜底（半权）
        os_label = f"{asset.os_name or ''} {asset.os_version or ''}".strip().lower()
        if os_label:
            eol_date = None
            for name, d in rules["health"]["eol_systems"].items():
                if name in os_label:
                    eol_date = d
                    break
            score = rules["health"]["eol_score"] if eol_date else 0
            reasons = [f"OS: {(asset.os_name or '')} {(asset.os_version or '')}".strip()]
            reasons.append(f"已过 EOL（{eol_date}）" if eol_date else "OS 未过 EOL")
            reasons.append("无漏洞扫描数据，仅按 OS 生命周期判断（维度按 50% 权重计入）")
            return {"score": score, "data_gap": True, "reasons": reasons, "inputs": {"eol_date": eol_date}}

        return {"score": 0, "data_gap": True,
                "reasons": ["无 OS 信息且无漏洞扫描数据（维度按 50% 权重计入）"], "inputs": {}}

    def _score_alerts(self, asset: Asset, rules: dict, now: datetime) -> dict:
        cfg = rules["alerts"]
        # 离线资产不参与告警密度计分（§4.5：无告警 ≠ 安全）→ 半权
        if (asset.asset_status or "").lower() == "offline":
            return {"score": 0, "data_gap": True,
                    "reasons": ["资产离线，告警密度不参与计分（无告警 ≠ 安全，按 50% 权重计入）"], "inputs": {}}
        since = now - timedelta(days=int(cfg["window_days"]))
        rows = (
            self.db.query(AlertGroupAnalysis)
            .filter(
                AlertGroupAnalysis.linked_asset_id == asset.id,
                AlertGroupAnalysis.created_at >= since,
            )
            .all()
        )
        score, counts = 0, {"P0": 0, "P1": 0, "P2": 0, "P3": 0}
        for r in rows:
            p = (r.priority or "P3").upper()
            if p in counts:
                counts[p] += 1
                score += cfg["priority_scores"][p]
        score = min(cfg["cap"], score)
        n = len(rows)
        reasons = [
            f"近 {cfg['window_days']} 天关联告警簇 {n} 个（P0/P1: {counts['P0'] + counts['P1']}）"
            if n else f"近 {cfg['window_days']} 天无关联告警簇"
        ]
        return {"score": score, "data_gap": False, "reasons": reasons,
                "inputs": {"window_days": cfg["window_days"], "priority_counts": counts}}

    def _score_importance(self, asset: Asset, rules: dict) -> dict:
        cfg = rules["importance"]
        crit = (asset.criticality or "medium").lower()
        base = cfg["criticality"].get(crit, cfg["criticality"]["medium"])
        dc = (asset.data_classification or "internal").lower()
        bonus = cfg["data_classification_bonus"].get(dc, 0)
        score = min(100, base + bonus)
        reasons = [f"重要性 {crit}" + (f"，数据分级 {dc}（+{bonus}）" if bonus else "")]
        return {"score": score, "data_gap": False, "reasons": reasons,
                "inputs": {"criticality": crit, "data_classification": dc}}

    # ---------- 聚合 ----------

    def score_asset(self, asset: Asset, rules: dict, now: Optional[datetime] = None) -> Optional[dict]:
        """纯计算，不落库。四维全缺 → None（N/A）。"""
        now = now or _utcnow()
        dims = {
            "exposure": self._score_exposure(asset, rules),
            "health": self._score_health(asset, rules),
            "alerts": self._score_alerts(asset, rules, now),
            "importance": self._score_importance(asset, rules),
        }
        # N/A 判定（§4.5）：三个证据维度（暴露面/健康/告警）全缺时，仅剩 importance
        # （资产价值配置，非风险证据）不足以支撑风险分 → 返回 None。
        # importance 因 criticality 有默认值永远可算，不参与 N/A 判定。
        if all(dims[k]["data_gap"] for k in ("exposure", "health", "alerts")):
            return None
        # 缺失维度按 50% 权重计入并重归一化（§4.5：保持 0-100 量纲）
        num = den = 0.0
        for name, d in dims.items():
            w = float(rules["weights"][name]) * (0.5 if d["data_gap"] else 1.0)
            d["weight"] = rules["weights"][name]
            d["effective_weight"] = round(w, 4)
            num += d["score"] * w
            den += w
        total = round(num / den) if den > 0 else 0
        return {
            "version": 1,
            "generated_at": now.isoformat(),
            "total": total,
            "dimensions": dims,
        }

    # ---------- 摘要（AI 增强，预算限流 + 降级） ----------

    @staticmethod
    def _fallback_summary(asset: Asset, breakdown: dict) -> str:
        """GLM 不可用时的规则化文案（§八-C 降级行为）。"""
        d = breakdown["dimensions"]
        parts = []
        exp = d["exposure"]
        if exp["inputs"].get("open_high_risk_ports"):
            parts.append(f"开放高危端口 {len(exp['inputs']['open_high_risk_ports'])} 个")
        if d["health"]["inputs"].get("open_vuln_counts"):
            c = d["health"]["inputs"]["open_vuln_counts"]
            parts.append(f"活跃漏洞 critical {c['critical']} / high {c['high']}")
        if d["health"]["inputs"].get("eol_date"):
            parts.append("运行已 EOL 系统")
        n_alerts = sum(d["alerts"]["inputs"].get("priority_counts", {}).values())
        if n_alerts:
            parts.append(f"近 {d['alerts']['inputs'].get('window_days', 7)} 天告警簇 {n_alerts} 个")
        if not parts:
            parts.append("未见明显风险因素")
        return f"该资产{'，'.join(parts)}。综合资产风险分 {breakdown['total']}/100（规则引擎口径）。"

    def generate_summary(self, asset: Asset, breakdown: dict, force: bool = False) -> tuple:
        """生成 GLM 摘要；返回 (text, source)。source: glm / rule / cached。"""
        cfg = rules = None  # noqa
        s_cfg = self.load_rules()["summary"]
        cache_seconds = int(s_cfg["cache_hours"]) * 3600
        if (
            not force
            and asset.risk_summary
            and asset.risk_scored_at
            and (_utcnow() - asset.risk_scored_at).total_seconds() < cache_seconds
        ):
            return asset.risk_summary, "cached"

        if not ai_budget.allow():
            return self._fallback_summary(asset, breakdown), "rule"

        try:
            from zhipuai import ZhipuAI
            from app.core.config import settings
            client = ZhipuAI(api_key=settings.GLM_API_KEY)
            compact = {
                "total": breakdown["total"],
                "dimensions": {
                    k: {"score": v["score"], "data_gap": v["data_gap"], "reasons": v["reasons"][:2]}
                    for k, v in breakdown["dimensions"].items()
                },
            }
            prompt = (
                "你是安全运营专家。基于资产风险评分明细，用一两句中文（不超过80字）概括该资产的主要风险，"
                "指出最关键的一两个因素，给出一个可操作建议。不要罗列全部数据，不要寒暄。\n"
                f"资产: {asset.name or asset.asset_ip} ({asset.asset_ip})，类型 {asset.asset_type}\n"
                f"OS: {(asset.os_name or '')} {(asset.os_version or '')}".strip() + "\n"
                f"评分明细(JSON): {json.dumps(compact, ensure_ascii=False)}"
            )
            resp = client.chat.completions.create(
                model=settings.GLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            text = (resp.choices[0].message.content or "").strip()
            ai_budget.record_success()
            if text:
                return text, "glm"
            return self._fallback_summary(asset, breakdown), "rule"
        except Exception as e:
            ai_budget.record_failure()
            logger.warning("风险摘要 GLM 调用失败，走规则化降级: %s", e)
            return self._fallback_summary(asset, breakdown), "rule"

    # ---------- 批量评分（落库 + 历史 + 摘要） ----------

    def _should_summarize(self, asset: Asset, total: int, prev_score: Optional[int], rules: dict) -> bool:
        s = rules["summary"]
        if total >= s["min_score"]:
            return True
        if prev_score is not None and total - prev_score >= s["rise_threshold"]:
            return True
        # 摘要已有且未过缓存期 → 不必重生成（generate_summary 内也会判 cached）
        return False

    def score_all(self, force_summaries: bool = False) -> dict:
        rules = self.load_rules()
        now = _utcnow()
        assets = self.db.query(Asset).all()
        stats = {"total_assets": len(assets), "scored": 0, "na": 0, "summaries": {"glm": 0, "rule": 0, "cached": 0, "skipped": 0}, "errors": 0}
        summaries_generated = 0
        summary_cap = int(rules["summary"]["per_run_cap"])

        for asset in assets:
            try:
                breakdown = self.score_asset(asset, rules, now)
                if breakdown is None:
                    asset.risk_score = None
                    asset.risk_summary = None
                    asset.risk_scored_at = now
                    stats["na"] += 1
                    continue

                # 7 天内上一条历史（本条插入前），用于上升检测
                prev = (
                    self.db.query(AssetRiskHistory)
                    .filter(
                        AssetRiskHistory.asset_id == asset.id,
                        AssetRiskHistory.scored_at >= now - timedelta(days=rules["summary"]["rise_window_days"]),
                    )
                    .order_by(AssetRiskHistory.scored_at.desc())
                    .first()
                )
                prev_score = prev.risk_score if prev else None
                if prev_score is not None:
                    breakdown["delta_7d"] = total_delta = breakdown["total"] - prev_score  # noqa: F841

                asset.risk_score = breakdown["total"]
                asset.risk_scored_at = now
                asset.score_breakdown = breakdown
                self.db.add(AssetRiskHistory(
                    asset_id=asset.id,
                    risk_score=breakdown["total"],
                    score_breakdown=breakdown,
                    scored_at=now,
                ))
                stats["scored"] += 1

                if force_summaries or self._should_summarize(asset, breakdown["total"], prev_score, rules):
                    if summaries_generated < summary_cap:
                        text, source = self.generate_summary(asset, breakdown)
                        asset.risk_summary = text
                        stats["summaries"][source if source in stats["summaries"] else "rule"] += 1
                        summaries_generated += 1
                    else:
                        stats["summaries"]["skipped"] += 1
                else:
                    # 低分资产摘要清空，避免陈旧摘要误导（前端展示 breakdown 模板即可）
                    if asset.risk_score < rules["summary"]["min_score"]:
                        asset.risk_summary = None
                    stats["summaries"]["skipped"] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.error("资产 %s 评分失败: %s", asset.id, e)

        self.db.commit()
        logger.info("批量风险评分完成: %s", stats)
        return stats

    # ---------- 查询 ----------

    def get_risk(self, asset_id) -> Optional[dict]:
        asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            return None
        return {
            "asset_id": str(asset.id),
            "asset_name": asset.name,
            "asset_ip": asset.asset_ip,
            "risk_score": asset.risk_score,
            "risk_summary": asset.risk_summary,
            "risk_scored_at": asset.risk_scored_at.isoformat() if asset.risk_scored_at else None,
            "score_breakdown": asset.score_breakdown,
            "summary_source": "glm" if (asset.risk_summary and "规则引擎口径" not in asset.risk_summary) else ("rule" if asset.risk_summary else None),
        }

    def get_history(self, asset_id, days: int = 90, limit: int = 120) -> list:
        since = _utcnow() - timedelta(days=days)
        rows = (
            self.db.query(AssetRiskHistory)
            .filter(AssetRiskHistory.asset_id == asset_id, AssetRiskHistory.scored_at >= since)
            .order_by(AssetRiskHistory.scored_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {"risk_score": r.risk_score, "scored_at": r.scored_at.isoformat(), "score_breakdown": r.score_breakdown}
            for r in reversed(rows)
        ]

    def overview(self) -> dict:
        assets = self.db.query(Asset).all()
        buckets = {"low": 0, "medium": 0, "high": 0, "critical": 0, "na": 0}
        scored = []
        now = _utcnow()
        for a in assets:
            s = a.risk_score
            if s is None:
                buckets["na"] += 1
            elif s >= 80:
                buckets["critical"] += 1
            elif s >= 60:
                buckets["high"] += 1
            elif s >= 40:
                buckets["medium"] += 1
            else:
                buckets["low"] += 1
            if s is not None:
                scored.append(a)
        top10 = sorted(scored, key=lambda a: a.risk_score, reverse=True)[:10]
        top10_list = [
            {"asset_id": str(a.id), "name": a.name, "ip": a.asset_ip,
             "risk_score": a.risk_score, "risk_summary": a.risk_summary}
            for a in top10
        ]

        # 评分上升最快（7 天窗口：最新分 - 窗口内最早分）
        rising = []
        for a in scored:
            rows = (
                self.db.query(AssetRiskHistory)
                .filter(
                    AssetRiskHistory.asset_id == a.id,
                    AssetRiskHistory.scored_at >= now - timedelta(days=7),
                )
                .order_by(AssetRiskHistory.scored_at.asc())
                .all()
            )
            if len(rows) >= 2:
                delta = a.risk_score - rows[0].risk_score
                if delta >= 10:
                    rising.append({"asset_id": str(a.id), "name": a.name, "ip": a.asset_ip,
                                   "risk_score": a.risk_score, "delta_7d": delta})
        rising.sort(key=lambda x: x["delta_7d"], reverse=True)

        return {
            "distribution": buckets,
            "total_assets": len(assets),
            "top10": top10_list,
            "rising": rising[:10],
            "budget": ai_budget.stats(),
        }
