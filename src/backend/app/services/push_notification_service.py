"""
主动推送服务（PRD F4.2，P3）

定位：让已建成的能力"主动找人"——复用 soc_notifications + WebSocket（零新增基础设施），
周期巡检两个已就绪的数据源，把异常推给全部活跃用户：

场景（PRD F4.2 表，F1.3/F2.2 就绪后已全部落地）：
1. 数据链路异常（critical）：soc_source_health 中断 ≥ down_hours（默认 3h；
   有 expected_interval 时取 max(down_hours, 2×周期)）
2. 风险评分突变（warn）：7 天窗口内评分上升 ≥ threshold（默认 20，复用 F1.1 历史）
3. EOL 临近（info/warn，F3.2 联动）：距 expected_eol ≤ info_days(30) 提醒一次、
   ≤ warn_days(7) 升级 warn；已超期也 warn；manual 覆盖同样纳入提醒
4. 影子资产发现（warn，F1.3 联动）：近 10 分钟内新增的 pending shadow 差异
5. 报告生成完成（info，F2.2 联动）：近 10 分钟内生成的 weekly/monthly/incident_driven

频控（PRD）：同类通知去重——dedup key 存 Notification.link（push:<场景>:<对象>），
info/warn 24h、critical 6h（critical 支持重复提醒）。

规则外置：soc_system_config(category='push_rules')，60s 缓存，admin 可调（PUT API）。
接收人：全部 active 用户（PRD X1：所有角色均接收通知）。
"""
import json
import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Asset
from app.models.asset_risk import AssetRiskHistory
from app.models.asset_reconciliation import AssetReconciliation, TYPE_SHADOW
from app.models.notification import Notification
from app.models.scanner_models import ScannerAgent
from app.models.security_report import SecurityReport
from app.models.source_health import SourceHealth
from app.models.user import User, UserStatus
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)

RULES_CATEGORY = "push_rules"
RULES_KEY = "rules"
_CACHE_TTL = 60  # 秒

DEFAULT_PUSH_RULES: dict = {
    "enabled": True,
    "dedup_hours": 24,            # info/warn 同类去重窗口
    "critical_dedup_hours": 6,    # critical 允许更频繁重复提醒（PRD：critical 支持重复）
    "source_health": {"enabled": True, "down_hours": 3},
    "risk_jump": {"enabled": True, "threshold": 20, "window_days": 7},
    "eol": {"enabled": True, "warn_days": 7, "info_days": 30},
    # F4.2 补齐：场景3 影子资产发现（依赖 F1.3 对账页）、场景4 报告生成完成（依赖 F2.2）
    "shadow_assets": {"enabled": True, "lookback_minutes": 10},
    "report_completion": {"enabled": True, "lookback_minutes": 10,
                           "types": ["weekly", "monthly", "incident_driven"]},
    # P3 资产扫描控制面（final.md §9.2 + §13 RV-4）：
    # 场景6 scanner_offline（critical）：soc_scanner_agents.last_heartbeat 超阈值
    # 场景7 scanner_source_health（critical）：scanner:discovery/scanner:ports 通道异常
    #    — 实际复用 check_source_health()，对 scanner:* 键自动覆盖，无需另写场景。
    "scanner_offline": {"enabled": True, "offline_minutes": 90},
}

_rules_cache = {"value": None, "at": 0.0}
_cache_lock = threading.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class PushNotificationService:
    """主动推送：巡检 → 去重 → 通知（DB 落库 + WS 实时）"""

    def __init__(self, db: Session):
        self.db = db

    # ---------- 规则存取（模式对齐 alert_governance_config / risk_rules） ----------

    def load_rules(self, force: bool = False) -> dict:
        now = time.time()
        with _cache_lock:
            if not force and _rules_cache["value"] is not None and (now - _rules_cache["at"]) < _CACHE_TTL:
                return _rules_cache["value"]
        rules = DEFAULT_PUSH_RULES
        try:
            from app.models.system_config import SystemConfig
            row = (
                self.db.query(SystemConfig)
                .filter(SystemConfig.category == RULES_CATEGORY, SystemConfig.key == RULES_KEY)
                .first()
            )
            if row and row.value:
                rules = _deep_merge(DEFAULT_PUSH_RULES, json.loads(row.value))
        except Exception as e:
            logger.warning("读取 push_rules 失败，用默认规则: %s", e)
        with _cache_lock:
            _rules_cache["value"] = rules
            _rules_cache["at"] = now
        return rules

    def save_rules(self, override: dict, user_id: Optional[int] = None) -> dict:
        merged = _deep_merge(DEFAULT_PUSH_RULES, override or {})
        from app.models.system_config import SystemConfig
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
                value_type="json", description="主动推送规则（与默认深合并）",
                updated_by=user_id,
            ))
        self.db.commit()
        with _cache_lock:
            _rules_cache["value"] = None
            _rules_cache["at"] = 0.0
        return merged

    # ---------- 基础设施：接收人 + 去重 + 发送 ----------

    def _recipients(self) -> list:
        return [u.id for u in self.db.query(User).filter(User.status == UserStatus.ACTIVE).all()]

    def _already_notified(self, dedup_title: str, dedup_hours: int) -> bool:
        """同类去重：type='push' + 稳定 title 前缀（场景对象不变则前缀不变；
    尾部数字如 Δ分可变，不入去重键。link 保留纯导航职责）。"""
        since = _utcnow() - timedelta(hours=dedup_hours)
        return (
            self.db.query(Notification.id)
            .filter(
                Notification.type == "push",
                Notification.title.startswith(dedup_title, autoescape=True),
                Notification.created_at >= since,
            )
            .first()
            is not None
        )

    async def _push(self, dedup_title: str, severity: str, title: str, content: str,
                    link_path: Optional[str] = None) -> int:
        """去重通过后给全部活跃用户发通知（title=去重键，需稳定不变）。返回发送人数。"""
        rules = self.load_rules()
        dedup = rules["critical_dedup_hours"] if severity == "critical" else rules["dedup_hours"]
        if self._already_notified(dedup_title, dedup):
            return 0
        svc = NotificationService(self.db)
        sent = 0
        for uid in self._recipients():
            try:
                await svc.create(
                    user_id=uid, type="push",
                    title=title, content=content,
                    link=link_path,
                    push_ws=True,
                )
                sent += 1
            except Exception as e:  # noqa: BLE001
                logger.warning("推送通知失败 user=%s: %s", uid, e)
        logger.info("主动推送: %s severity=%s 发送 %d 人", dedup_title, severity, sent)
        return sent

    # ---------- 场景 1：数据链路异常（critical，§八-B 源健康的运营化消费） ----------

    def _find_source_anomalies(self, rules: dict) -> list:
        cfg = rules["source_health"]
        down_seconds = int(cfg["down_hours"]) * 3600
        out = []
        for s in self.db.query(SourceHealth).all():
            expected = s.expected_interval_seconds or 0
            threshold = max(down_seconds, expected * 2)
            if s.last_success_at is None:
                abnormal = (s.failure_count or 0) > 0
                down_for = None
            else:
                down_for = (_utcnow() - s.last_success_at).total_seconds()
                abnormal = down_for > threshold
            if abnormal:
                out.append({
                    "source": s,
                    "down_hours": round(down_for / 3600, 1) if down_for else None,
                    "threshold_hours": round(threshold / 3600, 1),
                })
        return out

    async def check_source_health(self) -> int:
        rules = self.load_rules()
        if not (rules.get("enabled") and rules["source_health"].get("enabled")):
            return 0
        sent_total = 0
        for item in self._find_source_anomalies(rules):
            s = item["source"]
            name = s.display_name or s.source_key
            down = f'已 {item["down_hours"]}h 无成功' if item["down_hours"] else "从未成功过"
            err = (s.last_failure_message or "").strip()[:120]
            sent = await self._push(
                dedup_title=f"【数据链路异常】{name}",
                severity="critical",
                title=f"【数据链路异常】{name}",
                content=(
                    f"数据源「{name}」（{s.source_type}）{down}"
                    f"（阈值 {item['threshold_hours']}h）。"
                    + (f"最近错误：{err}" if err else "")
                    + " 对账与报告的数据可能不完整，请检查采集链路。"
                ),
                link_path=None,  # 纯告警，无详情页；link 即 dedup key
            )
            sent_total += sent
        return sent_total

    # ---------- 场景 2：风险评分突变（warn，复用 F1.1 历史） ----------

    def _find_risk_jumps(self, rules: dict) -> list:
        cfg = rules["risk_jump"]
        threshold = int(cfg["threshold"])
        since = _utcnow() - timedelta(days=int(cfg["window_days"]))
        assets = self.db.query(Asset).filter(Asset.risk_score.isnot(None)).all()
        if not assets:
            return []
        # 两查询防 N+1（资产投影 + 窗口内最早分）
        first_by_asset: dict = {}
        count_by_asset: dict = {}
        hrows = (
            self.db.query(AssetRiskHistory.asset_id, AssetRiskHistory.risk_score)
            .filter(
                AssetRiskHistory.asset_id.in_([a.id for a in assets]),
                AssetRiskHistory.scored_at >= since,
            )
            .order_by(AssetRiskHistory.scored_at.asc())
            .all()
        )
        for h in hrows:  # asc 扫描，首条即窗口内最早
            first_by_asset.setdefault(h.asset_id, h.risk_score)
            count_by_asset[h.asset_id] = count_by_asset.get(h.asset_id, 0) + 1
        out = []
        for a in assets:
            if count_by_asset.get(a.id, 0) < 2:
                continue  # 单点无趋势可言
            delta = a.risk_score - first_by_asset[a.id]
            if delta >= threshold:
                out.append({"asset": a, "delta": delta, "from": first_by_asset[a.id]})
        out.sort(key=lambda x: x["delta"], reverse=True)
        return out

    async def check_risk_jump(self) -> int:
        rules = self.load_rules()
        if not (rules.get("enabled") and rules["risk_jump"].get("enabled")):
            return 0
        sent_total = 0
        for item in self._find_risk_jumps(rules)[:10]:  # 单轮最多 10 条，防刷屏
            a = item["asset"]
            sent = await self._push(
                dedup_title=f"【风险异动】{a.name or a.asset_ip}",
                severity="warn",
                title=f"【风险异动】{a.name or a.asset_ip} 评分上升 {item['delta']} 分",
                content=(
                    f"资产 {a.name or a.asset_ip}（{a.asset_ip}）近 "
                    f"{rules['risk_jump']['window_days']} 天风险评分从 {item['from']} 升至 "
                    f"{a.risk_score}（+{item['delta']}），建议查看风险明细确认新增暴露。"
                ),
                link_path=f"/assets/detail/{a.id}",
            )
            sent_total += sent
        return sent_total

    # ---------- 场景 3：EOL 临近（F3.2 联动；PRD：30 天 info / 7 天 warn） ----------

    async def check_eol(self) -> int:
        rules = self.load_rules()
        if not (rules.get("enabled") and rules["eol"].get("enabled")):
            return 0
        from datetime import date, datetime, timezone
        today = datetime.now(timezone.utc).date()
        warn_days = int(rules["eol"]["warn_days"])
        info_days = int(rules["eol"]["info_days"])
        sent_total = 0
        for a in self.db.query(Asset).filter(Asset.expected_eol.isnot(None)).all():
            days = (a.expected_eol - today).days
            if days < 0:
                severity, state = "warn", f"已超期 {abs(days)} 天"
                desc = f"已过 EOL {abs(days)} 天（{a.expected_eol.isoformat()}），系统无安全补丁，建议优先升级/下线"
            elif days <= warn_days:
                severity, state = "warn", f"仅剩 {days} 天"
                desc = f"距 EOL 仅 {days} 天（{a.expected_eol.isoformat()}），请尽快安排升级/替换"
            elif days <= info_days:
                severity, state = "info", f"剩 {days} 天"
                desc = f"距 EOL {days} 天（{a.expected_eol.isoformat()}），建议纳入升级规划"
            else:
                continue
            os_label = f"{a.os_name or ''} {a.os_version or ''}".strip()
            name = a.name or a.asset_ip
            # 去重键必须是 title 的稳定前缀（_already_notified 用 startswith），
            # 变动部分（剩余天数）放尾部，否则每轮巡检都会重复推送
            dedup_title = f"【EOL 提醒】{name}"
            sent = await self._push(
                dedup_title=dedup_title,
                severity=severity,
                title=f"{dedup_title} · {state}",
                content=(
                    f"资产 {name}（{a.asset_ip}）{('，系统 ' + os_label) if os_label else ''}。{desc}。"
                    + ("（EOL 日期为人工指定）" if a.expected_eol_source == "manual" else "")
                ),
                link_path=f"/assets/detail/{a.id}",
            )
            sent_total += sent
        return sent_total

    # ---------- 场景 4：影子资产发现（warn，依赖 F1.3 对账页） ----------

    def _find_new_shadows(self, rules: dict) -> list:
        """近 N 分钟内创建且 status='pending' 的 shadow 差异。

        为什么不查全部 pending：多轮轮询下不重推，dedup title 锁定到「<主键>」，
        dedup_hours 24h 也能防住偶发双推。
        """
        cfg = rules["shadow_assets"]
        since = _utcnow() - timedelta(minutes=int(cfg["lookback_minutes"]))
        rows = (
            self.db.query(AssetReconciliation)
            .filter(
                AssetReconciliation.reconciliation_type == TYPE_SHADOW,
                AssetReconciliation.status == "pending",
                AssetReconciliation.created_at >= since,
            )
            .order_by(AssetReconciliation.created_at.desc())
            .all()
        )
        out = []
        for r in rows:
            d = r.details or {}
            ag = d.get("agent") or {}
            out.append({
                "recon": r,
                "agent_id": ag.get("id", "?"),
                "agent_name": ag.get("name") or "（未命名）",
                "agent_ip": ag.get("ip") or "",
                "os_name": ag.get("os_name") or "",
            })
        return out

    async def check_shadow_assets(self) -> int:
        rules = self.load_rules()
        if not (rules.get("enabled") and rules["shadow_assets"].get("enabled")):
            return 0
        sent_total = 0
        for item in self._find_new_shadows(rules):
            rec = item["recon"]
            # 去重键锁定到差异主键，不限今天会跨轮重推的概率
            dedup_title = f"【影子资产】Agent {item['agent_id']}"
            ip = item["agent_ip"]
            ip_part = f"（IP {ip}）" if ip else ""
            os_part = item["os_name"] or "系统未知"
            sent = await self._push(
                dedup_title=dedup_title,
                severity="warn",
                title=f"{dedup_title} 新增",
                content=(
                    f"Wazuh 中存在 Agent {item['agent_id']} {item['agent_name']} "
                    f"{ip_part}，但台账中无对应资产记录（系统 {os_part}）。"
                    f"建议确认是否需补录入台账，或在 Wazuh 侧确认 Agent 合法。"
                ),
                link_path="/assets/reconciliation",
            )
            sent_total += sent
        return sent_total

    # ---------- 场景 5：报告生成完成（info，依赖 F2.2 报告页） ----------

    def _find_new_reports(self, rules: dict) -> list:
        """近 N 分钟内生成的报告。

        只推 weekly/monthly/incident_driven；on_demand 是用户自己点的、跳过。
        skip_scheduled=True 时跳过 system:scheduler 生成的（属于后台调度）。
        """
        cfg = rules["report_completion"]
        since = _utcnow() - timedelta(minutes=int(cfg["lookback_minutes"]))
        allowed = set(cfg.get("types") or [])
        if not allowed:
            return []
        rows = (
            self.db.query(SecurityReport)
            .filter(
                SecurityReport.created_at >= since,
                SecurityReport.report_type.in_(list(allowed)),
            )
            .order_by(SecurityReport.created_at.desc())
            .all()
        )
        return rows

    async def check_report_completion(self) -> int:
        rules = self.load_rules()
        if not (rules.get("enabled") and rules["report_completion"].get("enabled")):
            return 0
        sent_total = 0
        for r in self._find_new_reports(rules):
            dedup_title = f"【报告就绪】{r.title}"
            degraded = (r.data_coverage or {}).get("data_degraded", False)
            cov_note = "（数据降级，见报告数据说明）" if degraded else ""
            sent = await self._push(
                dedup_title=dedup_title,
                severity="info",
                title=f"{dedup_title}{cov_note}",
                content=(
                    f"{r.title} 已生成（触发人 {r.triggered_by or '系统'}）"
                    f"，可前往报告列表查看详情。"
                ),
                link_path=f"/reports/list",
            )
            sent_total += sent
        return sent_total

    # ---------- 巡检入口 ----------

    async def run_all(self) -> dict:
        """全部场景巡检（调度器与手动触发共用）。"""
        return {
            "source_health": await self.check_source_health(),
            "risk_jump": await self.check_risk_jump(),
            "eol": await self.check_eol(),
            "shadow_assets": await self.check_shadow_assets(),
            "report_completion": await self.check_report_completion(),
            "scanner_offline": await self.check_scanner_offline(),
        }

    # ---------- P3 资产扫描：场景6 scanner 离线告（final.md §13 RV-4） ----------

    async def check_scanner_offline(self) -> int:
        """扫描器 L1 心跳超时告警。

        判据：soc_scanner_agents.last_heartbeat < now - offline_minutes 且 status != 'offline'。
        复用 _push() 的 dedup 机制（同 scanner_id 不重复）。
        """
        rules = self.load_rules()
        if not (rules.get("enabled") and rules.get("scanner_offline", {}).get("enabled")):
            return 0
        offline_minutes = int(rules["scanner_offline"].get("offline_minutes", 90))
        cutoff = _utcnow() - timedelta(minutes=offline_minutes)
        # 只查 enabled=True 且 未已标 offline 的扫描器（避免重复推送）
        candidates = (
            self.db.query(ScannerAgent)
            .filter(
                ScannerAgent.enabled == True,                                       # noqa: E712
                ScannerAgent.status != "offline",
                ScannerAgent.last_heartbeat < cutoff,
            )
            .all()
        )
        sent_total = 0
        for a in candidates:
            # 计算离线时长（小时）
            offline_h = (cutoff - a.last_heartbeat).total_seconds() / 3600 if a.last_heartbeat else None
            sent = await self._push(
                dedup_title=f"【扫描器离线】{a.name}",
                severity="critical",
                title=f"【扫描器离线】{a.name}（{a.scanner_id[:8]}）",
                content=(
                    f"扫描器「{a.name}」（IP {a.ip or '?'}、{a.scanner_id[:8]}）已离线"
                    f"{offline_h:.1f}h（阈值 {offline_minutes/60:.1f}h）。"
                    f"最后心跳 {a.last_heartbeat.isoformat() if a.last_heartbeat else '从未'}。"
                    "控制面将自动跳过该扫描器的任务派发；"
                    "请检查扫描器主机状态 / 网络 / heartbeat 拉任务循环。"
                ),
                link_path="/assets/scan?tab=scanners",
            )
            sent_total += sent
        return sent_total
