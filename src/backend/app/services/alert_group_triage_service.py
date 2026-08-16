"""
告警簇 AI 研判编排服务（Phase 1）

- triage_top_groups(): 取 TopN 告警簇 → 组装簇签名（含源 IP/资产/样本）→ 逐簇 AI 研判
  → 合并 verdict 回簇 dict → 按 P0>P1>P2>P3 再 count 排序返回"今日必处理"清单。
- triage_one(): 单簇研判（供 REST / MCP 触发）。
- get_cached_verdict(): 取某簇缓存 verdict（无则 None）。

top_n 来自系统配置 alert_governance.triage_top_n（默认 20）。
"""
import asyncio
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import AlertGroupAnalysis
from app.services.alert_query import AlertQueryService
from app.services.ai_analysis import AIAnalysisService
from app.services.alert_governance_config import (
    get_triage_top_n,
    get_min_group_count,
    filter_noise_groups,
)

logger = logging.getLogger(__name__)

PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
_TRIAGE_SEMAPHORE = 5  # 并发 AI 调用上限，控制对智谱的压力


class AlertGroupTriageService:
    """告警簇研判编排服务"""

    def __init__(self, db: Session):
        self.db = db

    # P1-T2：原 _ensure_tables() 已移除，表由迁移 e2f3a4b5c6d7 保障

    # ── 公开方法 ──────────────────────────────────────

    async def triage_top_groups(
        self, hours: int = 24, top_n: Optional[int] = None, force_refresh: bool = False
    ) -> List[dict]:
        """对 TopN 告警簇做 AI 研判，返回带 verdict 的簇清单（按优先级排序）。"""
        # P1-T2：_ensure_tables() 已移除，表由迁移 e2f3a4b5c6d7 保障
        if top_n is None:
            top_n = get_triage_top_n(self.db)

        svc = AlertQueryService(self.db)
        groups = svc.get_alert_groups(
            hours=hours, min_count=get_min_group_count(self.db), limit=top_n
        ).get("groups", [])
        # Phase 2 噪声抑制：研判前移除命中 suppress 名单的簇（省 AI 配额）
        groups, suppressed = filter_noise_groups(groups, self.db)
        if suppressed:
            logger.info("噪声抑制：研判前移除 %s 个簇（省 AI 配额）", suppressed)
        ai = AIAnalysisService(self.db)

        sem = asyncio.Semaphore(_TRIAGE_SEMAPHORE)

        async def _one(g: dict) -> dict:
            sig = await self._build_signature(svc, g, hours)
            try:
                verdict = await ai.triage_alert_group(sig, force_refresh=force_refresh)
            except Exception as e:
                logger.warning("簇研判失败(fp=%s)，启发式兜底: %s", g.get("fingerprint"), e)
                verdict = ai._heuristic_verdict(sig)
            merged = dict(g)
            merged.update(self._verdict_to_group_fields(verdict))
            return merged

        async def _bounded(g: dict):
            async with sem:
                return await _one(g)

        results = await asyncio.gather(*[_bounded(g) for g in groups])
        out = list(results)
        out.sort(
            key=lambda x: (PRIORITY_RANK.get(x.get("ai_priority"), 9), -(x.get("count") or 0))
        )
        return out

    async def triage_one(
        self, fingerprint: str, hours: int = 24, force_refresh: bool = False
    ) -> dict:
        """单簇研判（供 REST POST /groups/{fp}/triage）。"""
        svc = AlertQueryService(self.db)
        try:
            detail = svc.get_alert_group_detail(fingerprint, hours=hours, sample_size=5)
        except ValueError:
            raise
        linked = detail.get("linked_asset") or {}
        samples = detail.get("samples") or []
        sig = {
            "fingerprint": fingerprint,
            "rule_id": detail.get("rule_id"),
            "agent_id": detail.get("agent_id"),
            "rule_description": detail.get("rule_description"),
            "agent_name": detail.get("agent_name"),
            "agent_ip": detail.get("agent_ip"),
            "count": detail.get("count"),
            "level_min": detail.get("level_min"),
            "level_max": detail.get("level_max"),
            "first_seen": detail.get("first_seen"),
            "last_seen": detail.get("last_seen"),
            "distinct_srcips": detail.get("distinct_srcips") or 0,
            "top_srcips": detail.get("top_srcips") or [],
            "linked_asset": linked,
            "linked_asset_id": linked.get("asset_id"),
            "sample_full_log": samples[0].get("full_log") if samples else None,
            "window_hours": hours,
        }
        ai = AIAnalysisService(self.db)
        return await ai.triage_alert_group(sig, force_refresh=force_refresh)

    def get_cached_verdict(self, fingerprint: str) -> Optional[dict]:
        """取某簇缓存 verdict；无或已过期返回 None。"""
        ai = AIAnalysisService(self.db)
        obj = ai._get_cached_group_analysis(fingerprint)
        return obj.to_dict() if obj else None

    # ── 内部辅助 ──────────────────────────────────────

    async def _build_signature(self, svc: AlertQueryService, g: dict, hours: int) -> dict:
        """组装簇签名：优先 detail（源 IP/资产/样本），失败降级到 group 自带字段。"""
        fp = g.get("fingerprint")
        sig = {
            "fingerprint": fp,
            "rule_id": g.get("rule_id"),
            "agent_id": g.get("agent_id"),
            "rule_description": g.get("rule_description"),
            "agent_name": g.get("agent_name"),
            "agent_ip": g.get("agent_ip"),
            "count": g.get("count"),
            "level_min": g.get("level_min"),
            "level_max": g.get("level_max"),
            "first_seen": g.get("first_seen"),
            "last_seen": g.get("last_seen"),
            "distinct_srcips": 0,
            "top_srcips": [],
            "linked_asset": None,
            "linked_asset_id": None,
            "sample_full_log": None,
            "window_hours": hours,
        }
        # 尽力用 detail 补充源 IP / 资产 / 样本日志
        try:
            detail = svc.get_alert_group_detail(fp, hours=hours, sample_size=3)
            sig["distinct_srcips"] = detail.get("distinct_srcips") or 0
            sig["top_srcips"] = detail.get("top_srcips") or []
            sig["linked_asset"] = detail.get("linked_asset")
            if detail.get("linked_asset"):
                sig["linked_asset_id"] = detail["linked_asset"].get("asset_id")
            samples = detail.get("samples") or []
            if samples:
                sig["sample_full_log"] = samples[0].get("full_log")
        except Exception as e:
            logger.warning("簇明细获取失败(fp=%s): %s", fp, e)

        # 兜底：group.sample 自带日志
        if not sig["sample_full_log"]:
            s = g.get("sample")
            if s:
                sig["sample_full_log"] = s.get("full_log")
        # 兜底：按 agent_ip 关联资产
        if not sig["linked_asset_id"] and g.get("agent_ip"):
            try:
                la = svc._find_asset(agent_id=g.get("agent_id"), agent_ip=g.get("agent_ip"))
                if la:
                    sig["linked_asset"] = la
                    sig["linked_asset_id"] = la.get("asset_id")
            except Exception:
                pass
        return sig

    @staticmethod
    def _verdict_to_group_fields(verdict: dict) -> dict:
        """把结构化 verdict 映射到簇 dict 的 ai_* 字段。"""
        return {
            "ai_priority": verdict.get("priority"),
            "ai_is_noise": verdict.get("is_noise"),
            "ai_confidence": verdict.get("confidence"),
            "ai_rationale": verdict.get("rationale"),
            "ai_action": verdict.get("recommended_action"),
            "ai_suggest_incident": verdict.get("suggest_incident"),
            "ai_source": verdict.get("source"),
            "ai_model": verdict.get("model_name"),
            "ai_verdict_at": verdict.get("created_at"),
        }
