"""
资产安全态势摘要服务（PRD F1.2，P3 W3）

定位：F1.2 是**增值层**——告警时间线（详情页告警 Tab，P0 交付）与事件关联
（asset_incidents API，P1 交付）均已存在，本服务只做一件事：
**把降噪后的告警簇 + 事件 + 风险分聚合成一段人话摘要**。

数据口径（复用，不新建关联）：
- 告警：`soc_alert_group_analyses`（P0 告警簇 AI 研判，含 linked_asset_id/priority/
  rule_description/is_noise），过滤 is_noise——这正是 PRD 要求的"复用 P0 告警聚合"
- 事件：`soc_asset_incidents` ↔ `soc_incidents`（P1 闭环）
- 风险：`soc_assets.risk_score / risk_summary`（F1.1 产出）

质量门槛（PRD §八-B/§八-C/X2，硬性）：
- 摘要必须带数据窗口标注（window_start/window_end + 各源计数），缺口显式说明，
  禁止用空数据编造趋势
- GLM 走 ai_budget 限流；不可用/拒绝 → 统计数字模板文案（§八-C 降级表）
- 缓存 12h（§4.2）：进程内 dict（单 worker 部署足够；重启丢失代价 = 1 次 GLM 调用）
"""
import json
import logging
import threading
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Asset, AlertGroupAnalysis
from app.models.incident import Incident
from app.models.asset_incident import AssetIncident
from app.services.ai_budget import ai_budget

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_DAYS = 30
CACHE_TTL_SECONDS = 12 * 3600
TOP_RULES = 5
OPEN_INCIDENT_STATUSES = {"open", "in_progress"}  # 对齐 Incident.status 模型注释

# 进程内缓存：asset_id(str) -> {"summary","source","stats","window","generated_at"}
_summary_cache: dict = {}
_cache_generated: dict = {}  # asset_id -> datetime（TTL 比较用，避免解析 isoformat）
_cache_lock = threading.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AssetSecurityService:
    """资产安全态势摘要：聚合 → GLM 摘要（预算限流 + 降级 + 溯源）"""

    def __init__(self, db: Session):
        self.db = db

    # ---------- 聚合（本地统计，零 GLM 成本） ----------

    def collect_stats(self, asset: Asset, days: int) -> dict:
        """聚合告警簇/事件/风险统计。窗口标注是硬性要求（X2）。"""
        now = _utcnow()
        since = now - timedelta(days=days)

        groups = (
            self.db.query(AlertGroupAnalysis)
            .filter(
                AlertGroupAnalysis.linked_asset_id == asset.id,
                AlertGroupAnalysis.created_at >= since,
                AlertGroupAnalysis.is_noise.is_(False),
            )
            .all()
        )
        prio = Counter((g.priority or "P3").upper() for g in groups)
        rules = Counter(
            (g.rule_description or "").strip()[:80]
            for g in groups if g.rule_description
        )

        inc_rows = (
            self.db.query(Incident)
            .join(AssetIncident, AssetIncident.incident_id == Incident.id)
            .filter(AssetIncident.asset_id == asset.id)
            .all()
        )
        open_inc = [i for i in inc_rows if (i.status or "open").lower() in OPEN_INCIDENT_STATUSES]

        return {
            "asset": {"name": asset.name, "ip": asset.asset_ip,
                      "os": f"{asset.os_name or ''} {asset.os_version or ''}".strip(),
                      "criticality": asset.criticality},
            "window": {"days": days, "start": since.isoformat(), "end": now.isoformat()},
            "alert_groups": {
                "total": len(groups),
                "by_priority": {p: prio.get(p, 0) for p in ("P0", "P1", "P2", "P3")},
                "top_rules": [{"description": d, "count": c} for d, c in rules.most_common(TOP_RULES)],
            },
            "incidents": {
                "total": len(inc_rows),
                "open": len(open_inc),
                "recent": [
                    {"title": (i.title or "未命名")[:60], "status": i.status,
                     "severity": getattr(i, "severity", None)}
                    for i in sorted(inc_rows, key=lambda x: x.created_at or since, reverse=True)[:3]
                ],
            },
            "risk": {"risk_score": asset.risk_score,
                     "risk_summary": asset.risk_summary},
            # 数据新鲜度（§八-B）：告警簇数据是否有缺口
            "latest_group_at": max((g.created_at for g in groups), default=None).isoformat()
            if groups else None,
        }

    # ---------- 摘要生成 ----------

    @staticmethod
    def _fallback_summary(stats: dict) -> str:
        """降级文案：纯统计数字模板（§八-C），带数据窗口，不编造。"""
        g = stats["alert_groups"]
        inc = stats["incidents"]
        risk = stats["risk"]
        parts = []
        if g["total"]:
            high = g["by_priority"]["P0"] + g["by_priority"]["P1"]
            top = g["top_rules"][0] if g["top_rules"] else None
            parts.append(
                f"近 {stats['window']['days']} 天该资产命中告警簇 {g['total']} 个"
                f"（高危 {high}）" + (f"，主要为「{top['description']}」（{top['count']} 次）" if top else "")
            )
        else:
            parts.append(f"近 {stats['window']['days']} 天无降噪后告警簇记录")
        if inc["total"]:
            parts.append(f"关联事件 {inc['total']} 个（未关闭 {inc['open']}）")
        if risk["risk_score"] is not None:
            parts.append(f"资产风险分 {risk['risk_score']}/100")
        return "。".join(parts) + "。（统计口径生成，AI 摘要暂不可用）"

    def _generate_glm(self, stats: dict) -> Optional[str]:
        if not ai_budget.allow():
            return None
        try:
            from zhipuai import ZhipuAI
            from app.core.config import settings
            client = ZhipuAI(api_key=settings.GLM_API_KEY)
            compact = {
                "asset": stats["asset"],
                "window_days": stats["window"]["days"],
                "alert_groups": stats["alert_groups"],
                "incidents": stats["incidents"],
                "risk_score": stats["risk"]["risk_score"],
            }
            prompt = (
                "你是安全运营专家。基于资产近段时间的安全统计数据，用 2-3 句中文（不超过120字）"
                "概括该资产的安全态势：主要威胁是什么、是否在恶化、最该做什么。"
                "引用具体数字；若告警为 0 且无事件，如实说明并给一条加固建议；不要寒暄、不要罗列全部数据。\n"
                f"统计数据(JSON): {json.dumps(compact, ensure_ascii=False)}"
            )
            resp = client.chat.completions.create(
                model=settings.GLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            ai_budget.record_success()
            text = (resp.choices[0].message.content or "").strip()
            return text or None
        except Exception as e:
            ai_budget.record_failure()
            logger.warning("安全态势摘要 GLM 失败，走统计降级: %s", e)
            return None

    def security_summary(self, asset_id, days: int = DEFAULT_WINDOW_DAYS,
                         force: bool = False) -> Optional[dict]:
        """主入口：命中缓存 → 直接返回；否则聚合 → GLM/降级 → 缓存。"""
        asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset:
            return None
        key = str(asset.id)
        days = min(max(days, 1), 90)

        if not force:
            with _cache_lock:
                hit = _summary_cache.get(key)
                hit_ts = _cache_generated.get(key)
                if hit and hit_ts and (_utcnow() - hit_ts).total_seconds() < CACHE_TTL_SECONDS:
                    return hit

        stats = self.collect_stats(asset, days)
        text = self._generate_glm(stats)
        source = "glm"
        if text is None:
            text = self._fallback_summary(stats)
            source = "rule"
        generated_at = _utcnow()
        result = {
            "asset_id": key,
            "summary": text,
            "summary_source": source,
            "stats": stats,           # 前端可展开：窗口标注 + 分布 + top 规则（X2 溯源）
            "generated_at": generated_at.isoformat(),
        }
        with _cache_lock:
            _summary_cache[key] = result
            _cache_generated[key] = generated_at  # datetime 原始值，供 TTL 比较
        return result

    @staticmethod
    def invalidate(asset_id) -> None:
        with _cache_lock:
            _summary_cache.pop(str(asset_id), None)
            _cache_generated.pop(str(asset_id), None)
