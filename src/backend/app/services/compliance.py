"""
合规基线判定引擎（PRD F3.3）

【本文件不含任何 LLM 调用——这是设计红线】
判定 = 纯函数(规则, 资产字段快照) → pass / fail / unknown。
同样输入必得同样输出，审计可复算、可对质。AI 解读在 compliance_ai.py，
只读 fail 结果生成整改建议，无法反向影响判定。

三态语义：
  pass    明确达标
  fail    明确不达标（evidence 记录当时读到的实际值）
  unknown 数据缺失，无法判定 —— 绝不当作达标

达标率口径（防审计造假）：
  compliance_rate = pass / (pass + fail)
  coverage_rate   = (pass + fail) / (pass + fail + unknown)
  两者必须同时呈现。DEV 实测 73 台资产中仅 17 台有端口数据，
  若把 unknown 算作 pass，「高危端口达标率」会虚高成 100%。
"""
from __future__ import annotations

import logging
import threading
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import yaml
from sqlalchemy.orm import Session

from app.models import Asset, ComplianceFinding, ComplianceRun
from app.models.asset_port import AssetPort

logger = logging.getLogger(__name__)

# 规则库路径：项目根 configs/compliance_rules.yaml
_RULES_PATH = Path(__file__).resolve().parents[4] / "configs" / "compliance_rules.yaml"

_ruleset_cache: dict = {"value": None, "mtime": 0.0}
_cache_lock = threading.Lock()

IN_SCOPE_STATUS = ("online", "active")


# ---------------------------------------------------------------------------
# 规则库加载
# ---------------------------------------------------------------------------

def load_ruleset(force: bool = False) -> dict:
    """加载规则库（按文件 mtime 自动失效，改 YAML 无需重启）。"""
    with _cache_lock:
        try:
            mtime = _RULES_PATH.stat().st_mtime
        except OSError:
            logger.error("合规规则库不存在: %s", _RULES_PATH)
            return {"ruleset_version": "0", "rules": []}
        if not force and _ruleset_cache["value"] is not None and _ruleset_cache["mtime"] == mtime:
            return _ruleset_cache["value"]
        with open(_RULES_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        rules = data.get("rules") or []
        # 校验：id 唯一 + check.type 在白名单内。
        # 单条坏规则不该搞挂整个巡检，但也绝不静默丢弃——合规场景下「规则悄悄消失」
        # 比报错更危险（报告会少算一条而无人察觉）。故非法规则连同原因放进
        # invalid_rules，由 API / 页面显式告警。
        seen, valid, invalid = set(), [], []
        for idx, r in enumerate(rules):
            rid = r.get("id")
            ctype = (r.get("check") or {}).get("type")
            if not rid:
                invalid.append({"id": f"(第 {idx + 1} 条无 id)", "reason": "缺少 id 字段"})
                logger.error("合规规则第 %d 条缺少 id，已跳过", idx + 1)
                continue
            if rid in seen:
                invalid.append({"id": rid, "reason": "id 重复"})
                logger.error("合规规则 id 重复，已跳过: %s", rid)
                continue
            if ctype not in _CHECKERS:
                invalid.append({"id": rid, "reason": f"判定类型 {ctype} 不在白名单"})
                logger.error("合规规则 %s 的 check.type=%s 不在白名单，已跳过", rid, ctype)
                continue
            seen.add(rid)
            valid.append(r)
        data["rules"] = valid
        data["invalid_rules"] = invalid
        _ruleset_cache["value"] = data
        _ruleset_cache["mtime"] = mtime
        if invalid:
            logger.error("合规规则库 v%s 有 %d 条规则未能加载，巡检覆盖不完整: %s",
                         data.get("ruleset_version"), len(invalid), invalid)
        logger.info("合规规则库已加载: v%s, %d 条规则（失效 %d 条）",
                    data.get("ruleset_version"), len(valid), len(invalid))
        return data


# ---------------------------------------------------------------------------
# 判定器白名单（不支持 eval / 自由表达式：配置不得成为执行入口）
# ---------------------------------------------------------------------------

class Ctx:
    """判定上下文：资产 + 预取的关联数据（端口等）"""

    def __init__(self, asset: Asset, ports: Optional[list[AssetPort]]):
        self.asset = asset
        # None 表示「未采集过端口」→ 端口类规则 unknown；[] 表示「扫过但无开放端口」→ 可判 pass
        self.ports = ports

    @property
    def open_ports(self) -> list[int]:
        return [p.port for p in (self.ports or []) if p.state == "open"]


def _chk_ports_absent(ctx: Ctx, cfg: dict) -> tuple[str, str, dict]:
    """指定端口集合不得开放

    纵深防御：即使规则作者忘写 requires: [ports]，未采集过端口也必须落 unknown。
    否则「没数据」会被当成「没问题」，是合规类系统最典型的假阳性漏洞。
    """
    if ctx.ports is None:
        return "unknown", "该资产无端口扫描数据，无法判定端口开放情况", {"ports": None}
    forbidden = set(cfg.get("ports") or [])
    hit = sorted(set(ctx.open_ports) & forbidden)
    ev = {"open_ports": sorted(set(ctx.open_ports)), "forbidden": sorted(forbidden), "hit": hit}
    if hit:
        return "fail", f"开放了受限端口 {', '.join(map(str, hit))}", ev
    return "pass", "未开放受限端口", ev


def _chk_high_risk_port_count_max(ctx: Ctx, cfg: dict) -> tuple[str, str, dict]:
    if ctx.ports is None:
        return "unknown", "该资产无端口扫描数据，无法统计高危端口数", {"ports": None}
    watch = set(cfg.get("ports") or [])
    limit = int(cfg.get("max", 3))
    hit = sorted(set(ctx.open_ports) & watch)
    ev = {"high_risk_open": hit, "count": len(hit), "max": limit}
    if len(hit) > limit:
        return "fail", f"开放 {len(hit)} 个高危端口（上限 {limit}）：{', '.join(map(str, hit))}", ev
    return "pass", f"高危端口 {len(hit)} 个，未超上限 {limit}", ev


def _chk_fields_not_empty(ctx: Ctx, cfg: dict) -> tuple[str, str, dict]:
    fields = cfg.get("fields") or []
    missing, ev = [], {}
    for f in fields:
        v = getattr(ctx.asset, f, None)
        ev[f] = v if v is None or isinstance(v, (str, int, float, bool)) else str(v)
        if v is None or (isinstance(v, str) and not v.strip()):
            missing.append(f)
    if missing:
        return "fail", f"必填字段为空：{', '.join(missing)}", ev
    return "pass", "必填字段完整", ev


def _chk_field_in(ctx: Ctx, cfg: dict) -> tuple[str, str, dict]:
    """字段取值必须在允许集合内（用于字典合法性校验）"""
    f = cfg["field"]
    allowed = cfg.get("allowed") or []
    v = getattr(ctx.asset, f, None)
    ev = {f: v, "allowed": allowed}
    if v is None or (isinstance(v, str) and not v.strip()):
        return "unknown", f"字段 {f} 无值，无法判定", ev
    if v not in allowed:
        return "fail", f"{f}={v} 不在字典定义集合 {allowed} 中", ev
    return "pass", f"{f}={v} 合法", ev


def _chk_field_not_in(ctx: Ctx, cfg: dict) -> tuple[str, str, dict]:
    f = cfg["field"]
    forbidden = set(cfg.get("forbidden") or [])
    v = getattr(ctx.asset, f, None)
    ev = {f: v, "forbidden": sorted(forbidden)}
    if v is None:
        return "unknown", f"字段 {f} 无值，无法判定", ev
    if v in forbidden:
        return "fail", f"{f}={v} 属于不允许取值", ev
    return "pass", f"{f}={v} 合规", ev


def _chk_date_not_passed(ctx: Ctx, cfg: dict) -> tuple[str, str, dict]:
    f = cfg["field"]
    v = getattr(ctx.asset, f, None)
    ev = {f: v.isoformat() if isinstance(v, date) else v}
    if v is None:
        return "unknown", f"{f} 无值，无法判定", ev
    days = (v - date.today()).days
    ev["days_left"] = days
    if days < 0:
        return "fail", f"{f}={v.isoformat()} 已超期 {abs(days)} 天", ev
    return "pass", f"{f}={v.isoformat()}，剩余 {days} 天", ev


def _chk_date_days_remaining_min(ctx: Ctx, cfg: dict) -> tuple[str, str, dict]:
    f = cfg["field"]
    min_days = int(cfg.get("min_days", 90))
    v = getattr(ctx.asset, f, None)
    ev = {f: v.isoformat() if isinstance(v, date) else v, "min_days": min_days}
    if v is None:
        return "unknown", f"{f} 无值，无法判定", ev
    days = (v - date.today()).days
    ev["days_left"] = days
    if days < 0:
        # 已超期由 SOC-SYS-001 专管，此处不重复报 fail，避免同一问题双计
        return "pass", f"已超期，由 EOL 超期规则单独判定", ev
    if days < min_days:
        return "fail", f"距 {f} 仅 {days} 天（要求 ≥{min_days} 天需有升级计划）", ev
    return "pass", f"距 {f} {days} 天，充裕", ev


def _chk_timestamp_within_days(ctx: Ctx, cfg: dict) -> tuple[str, str, dict]:
    f = cfg["field"]
    max_days = int(cfg.get("max_days", 7))
    v = getattr(ctx.asset, f, None)
    ev = {f: v.isoformat() if isinstance(v, datetime) else v, "max_days": max_days}
    if v is None:
        return "unknown", f"{f} 无值，无法判定", ev
    if v.tzinfo is None:
        v = v.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - v).days
    ev["age_days"] = age
    if age > max_days:
        return "fail", f"{f} 已过时 {age} 天（要求 ≤{max_days} 天）", ev
    return "pass", f"{f} 距今 {age} 天，数据新鲜", ev


def _chk_number_max(ctx: Ctx, cfg: dict) -> tuple[str, str, dict]:
    f = cfg["field"]
    limit = cfg["max"]
    v = getattr(ctx.asset, f, None)
    ev = {f: v, "max": limit}
    if v is None:
        return "unknown", f"{f} 无值，无法判定", ev
    if v > limit:
        return "fail", f"{f}={v}，超过上限 {limit}", ev
    return "pass", f"{f}={v}，未超上限 {limit}", ev


_CHECKERS: dict[str, Callable[[Ctx, dict], tuple[str, str, dict]]] = {
    "ports_absent": _chk_ports_absent,
    "high_risk_port_count_max": _chk_high_risk_port_count_max,
    "fields_not_empty": _chk_fields_not_empty,
    "field_in": _chk_field_in,
    "field_not_in": _chk_field_not_in,
    "date_not_passed": _chk_date_not_passed,
    "date_days_remaining_min": _chk_date_days_remaining_min,
    "timestamp_within_days": _chk_timestamp_within_days,
    "number_max": _chk_number_max,
}


# ---------------------------------------------------------------------------
# 数据依赖检查（requires）
# ---------------------------------------------------------------------------

def _dependency_missing(ctx: Ctx, requires: list[str]) -> Optional[str]:
    """返回缺失依赖的说明；None 表示依赖齐备"""
    for dep in requires or []:
        if dep == "ports":
            if ctx.ports is None:
                return "该资产无端口扫描数据"
        elif dep == "expected_eol":
            if ctx.asset.expected_eol is None:
                return "该资产无 EOL 数据（OS 信息缺失或参考表无对应条目）"
        elif dep == "risk_score":
            if ctx.asset.risk_score is None:
                return "该资产尚未评分"
        elif dep == "last_synced_at":
            if ctx.asset.last_synced_at is None:
                return "该资产无同步时间（手工录入未纳入采集）"
        else:
            v = getattr(ctx.asset, dep, None)
            if v is None or (isinstance(v, str) and not v.strip()):
                return f"依赖字段 {dep} 缺失"
    return None


def _in_scope(asset: Asset, scope: dict) -> bool:
    """规则适用范围：scope 中每个键的值列表须包含资产实际值"""
    for field, allowed in (scope or {}).items():
        v = getattr(asset, field, None)
        if v not in (allowed or []):
            return False
    return True


# ---------------------------------------------------------------------------
# 服务主体
# ---------------------------------------------------------------------------

class ComplianceService:
    """合规判定服务（判定层，零 LLM）"""

    def __init__(self, db: Session):
        self.db = db

    # ---------- 单资产（详情页即时重算，不落库） ----------

    def evaluate_asset(self, asset: Asset, ports: Optional[list[AssetPort]] = None) -> dict:
        """对单个资产跑全部规则，返回逐规则结果（含 pass），用于详情页展示。"""
        rs = load_ruleset()
        if ports is None:
            ports = self._ports_for([asset.id]).get(asset.id)
        ctx = Ctx(asset, ports)
        items = []
        for rule in rs["rules"]:
            items.append(self._eval_one(ctx, rule))
        counts = {s: sum(1 for i in items if i["status"] == s)
                  for s in ("pass", "fail", "unknown", "skipped")}
        return {
            "ruleset_version": rs.get("ruleset_version"),
            "asset_id": str(asset.id),
            "counts": counts,
            "compliance_rate": self._rate(counts["pass"], counts["fail"]),
            "items": items,
        }

    def _eval_one(self, ctx: Ctx, rule: dict) -> dict:
        base = {
            "rule_id": rule["id"],
            "rule_version": rule.get("version", 1),
            "title": rule.get("title"),
            "category": rule.get("category"),
            "severity": rule.get("severity"),
            "baseline": rule.get("baseline"),
            "rationale": rule.get("rationale"),
            "remediation_hint": rule.get("remediation_hint"),
        }
        # 1) 适用范围
        if not _in_scope(ctx.asset, rule.get("scope")):
            return {**base, "status": "skipped", "reason": "不在该规则适用范围", "evidence": {}}
        # 2) 数据依赖
        miss = _dependency_missing(ctx, rule.get("requires"))
        if miss:
            return {**base, "status": "unknown", "reason": miss, "evidence": {}}
        # 3) 判定
        checker = _CHECKERS[rule["check"]["type"]]
        try:
            status, reason, ev = checker(ctx, rule["check"])
        except Exception as e:  # noqa: BLE001 —— 判定器异常按 unknown 处理，绝不静默 pass
            logger.exception("规则 %s 判定异常", rule["id"])
            return {**base, "status": "unknown", "reason": f"判定异常：{e}", "evidence": {}}
        return {**base, "status": status, "reason": reason, "evidence": ev}

    # ---------- 全量巡检（落库） ----------

    def run_check(self, triggered_by: str = "manual") -> ComplianceRun:
        rs = load_ruleset()
        rules = rs["rules"]

        all_assets = self.db.query(Asset).all()
        in_scope = [a for a in all_assets if (a.asset_status or "") in IN_SCOPE_STATUS]
        ports_map = self._ports_for([a.id for a in in_scope])

        totals = {"pass": 0, "fail": 0, "unknown": 0, "skipped": 0}
        per_rule: dict[str, dict] = {
            r["id"]: {"title": r.get("title"), "severity": r.get("severity"),
                      "category": r.get("category"), "version": r.get("version", 1),
                      "pass": 0, "fail": 0, "unknown": 0, "skipped": 0}
            for r in rules
        }
        per_severity: dict[str, int] = {}
        findings: list[ComplianceFinding] = []

        for asset in in_scope:
            ctx = Ctx(asset, ports_map.get(asset.id))
            for rule in rules:
                res = self._eval_one(ctx, rule)
                st = res["status"]
                totals[st] += 1
                per_rule[rule["id"]][st] += 1
                if st in ("fail", "unknown"):
                    if st == "fail":
                        sev = res.get("severity") or "medium"
                        per_severity[sev] = per_severity.get(sev, 0) + 1
                    findings.append(ComplianceFinding(
                        asset_id=asset.id,
                        rule_id=res["rule_id"], rule_version=res["rule_version"],
                        rule_title=res["title"], category=res["category"],
                        severity=res["severity"], status=st,
                        reason=res["reason"], evidence=res["evidence"] or {},
                    ))

        run = ComplianceRun(
            ruleset_version=str(rs.get("ruleset_version")),
            ruleset_name=rs.get("ruleset_name"),
            rules_total=len(rules),
            assets_total=len(all_assets),
            assets_in_scope=len(in_scope),
            pass_count=totals["pass"], fail_count=totals["fail"],
            unknown_count=totals["unknown"],
            compliance_rate=self._rate(totals["pass"], totals["fail"]),
            coverage_rate=self._rate(totals["pass"] + totals["fail"], totals["unknown"]),
            stats={
                "per_rule": per_rule,
                "fail_by_severity": per_severity,
                "skipped_total": totals["skipped"],
                "notes": (load_ruleset().get("notes") or {}),
            },
            triggered_by=triggered_by,
        )
        self.db.add(run)
        self.db.flush()
        for f in findings:
            f.run_id = run.id
        self.db.add_all(findings)
        self.db.commit()
        self.db.refresh(run)
        logger.info("合规巡检完成 v%s: pass=%d fail=%d unknown=%d 达标率=%s%% 覆盖率=%s%%",
                    run.ruleset_version, run.pass_count, run.fail_count,
                    run.unknown_count, run.compliance_rate, run.coverage_rate)
        return run

    # ---------- 查询 ----------

    def latest_run(self) -> Optional[ComplianceRun]:
        return (self.db.query(ComplianceRun)
                .order_by(ComplianceRun.created_at.desc()).first())

    def findings(self, run_id, status: Optional[str] = None,
                 severity: Optional[str] = None, rule_id: Optional[str] = None,
                 page: int = 1, page_size: int = 20) -> dict:
        q = self.db.query(ComplianceFinding).filter(ComplianceFinding.run_id == run_id)
        if status:
            q = q.filter(ComplianceFinding.status == status)
        if severity:
            q = q.filter(ComplianceFinding.severity == severity)
        if rule_id:
            q = q.filter(ComplianceFinding.rule_id == rule_id)
        total = q.count()
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        rows = q.all()
        rows.sort(key=lambda f: (f.status != "fail",
                                 sev_order.get(f.severity or "medium", 9),
                                 f.rule_id))
        start = (page - 1) * page_size
        return {"total": total, "page": page, "page_size": page_size,
                "records": rows[start:start + page_size]}

    # ---------- 内部 ----------

    def _ports_for(self, asset_ids: list) -> dict:
        """批量取端口。返回 {asset_id: [ports]}；无记录的 key 不存在（→ ports=None → unknown）"""
        if not asset_ids:
            return {}
        rows = (self.db.query(AssetPort)
                .filter(AssetPort.asset_id.in_(asset_ids)).all())
        out: dict = {}
        for p in rows:
            out.setdefault(p.asset_id, []).append(p)
        return out

    @staticmethod
    def _rate(numerator: int, other: int) -> Optional[int]:
        denom = numerator + other
        if denom == 0:
            return None
        return round(numerator * 100 / denom)
