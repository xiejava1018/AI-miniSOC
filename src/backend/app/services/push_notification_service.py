"""
主动推送服务（PRD F4.2，P3）

定位：让已建成的能力"主动找人"——复用 soc_notifications + WebSocket（零新增基础设施），
周期巡检两个已就绪的数据源，把异常推给全部活跃用户：

场景（PRD F4.2 表，已落地 3 个；报告完成场景依赖 F2.2，影子资产依赖 F1.3，
建成后按同模式扩展）：
1. 数据链路异常（critical）：soc_source_health 中断 ≥ down_hours（默认 3h；
   有 expected_interval 时取 max(down_hours, 2×周期)）
2. 风险评分突变（warn）：7 天窗口内评分上升 ≥ threshold（默认 20，复用 F1.1 历史）
3. EOL 临近（info/warn，F3.2 联动）：距 expected_eol ≤ info_days(30) 提醒一次、
   ≤ warn_days(7) 升级 warn；已超期也 warn；manual 覆盖同样纳入提醒

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
from app.models.notification import Notification
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

    # ---------- 巡检入口 ----------

    async def run_all(self) -> dict:
        """全部场景巡检（调度器与手动触发共用）。"""
        return {
            "source_health": await self.check_source_health(),
            "risk_jump": await self.check_risk_jump(),
            "eol": await self.check_eol(),
        }
