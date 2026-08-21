"""对账 AI 报告（P3 / F1.3 的 AI 增强部分）

职责边界（PRD §1.3 设计原则："判定交给规则引擎，解读交给 LLM"）：
  判定  → asset_reconciliation.py 已完成，本模块**不改变任何结论**
  解读  → 本模块把差异列表讲成运维能直接照做的话

三条硬约束：
  1. 走 ai_budget 限流；预算耗尽/未配 Key 时降级为模板文案，而不是报错或空白。
  2. 数据不新鲜时（freshness.degraded）报告开头必须先声明可信度，
     禁止在源异常时给出干净的"一切正常"结论。
  3. 标注数据窗口与来源（X2 AI 产物可追溯性）。
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.core.config import settings
from app.models.asset_reconciliation import (
    TYPE_MISMATCH,
    TYPE_OFFLINE,
    TYPE_SHADOW,
)
from app.services.ai_budget import ai_budget
from app.services.asset_reconciliation import AssetReconciliationService

logger = logging.getLogger(__name__)

PROMPT_VERSION = "recon-report-v1"
_MAX_ITEMS_IN_PROMPT = 12  # 控制 token；差异再多也只举例，总数由规则侧给准数

_TYPE_LABEL = {
    TYPE_SHADOW: "影子资产",
    TYPE_OFFLINE: "疑似下线",
    TYPE_MISMATCH: "信息不一致",
}


class ReconciliationReportService:
    def __init__(self, db):
        self.db = db
        self.svc = AssetReconciliationService(db)

    def report(self, run_id: Optional[uuid.UUID] = None, force: bool = False) -> dict:
        summary = self.svc.summary(run_id)
        if not summary.get("has_data"):
            return {
                **summary,
                "report": "尚未执行过对账，暂无报告。请先点击「立即对账」。",
                "source": "none",
                "prompt_version": PROMPT_VERSION,
            }

        rid = uuid.UUID(summary["run_id"])
        items = self.svc.list_diffs(run_id=rid, page=1, page_size=_MAX_ITEMS_IN_PROMPT)
        facts = self._facts(summary, items["records"])

        text, source = None, "template"
        if force or self._worth_ai(summary):
            text = self._glm_report(facts)
            if text:
                source = "glm"
        if not text:
            text = self._template_report(summary, items["records"])

        return {
            **summary,
            "report": text,
            "source": source,
            "prompt_version": PROMPT_VERSION,
            # X2 可追溯性：这份报告基于哪个批次、多少条差异、数据是否可信
            "provenance": {
                "run_id": summary["run_id"],
                "diff_total": summary.get("diff_total", 0),
                "items_in_prompt": len(items["records"]),
                "checked_at": summary.get("checked_at"),
                "data_degraded": bool((summary.get("freshness") or {}).get("degraded")),
            },
        }

    @staticmethod
    def _worth_ai(summary: dict) -> bool:
        """无差异时不值得花 GLM 调用（成本可控原则），模板一句话就够。"""
        return (summary.get("diff_total") or 0) > 0

    def _facts(self, summary: dict, rows: list) -> str:
        fr = summary.get("freshness") or {}
        lines = [
            f"对账批次: {summary['run_id']}",
            f"对账时间: {summary.get('checked_at')}",
            f"差异总数: {summary.get('diff_total', 0)}",
            f"差异分布: {summary.get('by_type')}",
            f"数据可信度: {'降级（源异常，结果可能不全）' if fr.get('degraded') else '正常'}",
            f"台账最近成功同步: {fr.get('last_sync_at') or '无记录'}",
        ]
        if fr.get("unhealthy_sources"):
            lines.append(
                "异常数据源: "
                + ", ".join(s.get("source_key", "?") for s in fr["unhealthy_sources"])
            )
        if fr.get("dead_letter_pending"):
            lines.append(f"待处理同步死信: {fr['dead_letter_pending']} 条")

        lines.append("差异明细（最多 %d 条）:" % _MAX_ITEMS_IN_PROMPT)
        for r in rows:
            d = r.details or {}
            label = _TYPE_LABEL.get(r.reconciliation_type, r.reconciliation_type)
            if r.reconciliation_type == TYPE_SHADOW:
                ag = d.get("agent") or {}
                lines.append(
                    f"- [{label}] Agent {ag.get('id')} {ag.get('name')} "
                    f"IP={ag.get('ip')} OS={ag.get('os_name')} 状态={ag.get('status')}"
                )
            elif r.reconciliation_type == TYPE_OFFLINE:
                led = d.get("ledger") or {}
                extra = (
                    f"已断开 {d['disconnected_days']} 天"
                    if d.get("disconnected_days") is not None
                    else f"原因={d.get('reason')}"
                )
                lines.append(
                    f"- [{label}] 台账 {led.get('name')} IP={led.get('asset_ip')} {extra}"
                )
            else:
                led = d.get("ledger") or {}
                diffs = "; ".join(
                    f"{x.get('label')}: 台账={x.get('ledger_value')} 实际={x.get('actual_value')}"
                    for x in (d.get("diffs") or [])
                )
                ag = d.get("agent") or {}
                lines.append(f"- [{label}] {ag.get('name') or led.get('name')} {diffs}")
        return "\n".join(lines)

    def _glm_report(self, facts: str) -> Optional[str]:
        if not ai_budget.allow():
            logger.info("对账报告降级为模板：AI 预算/限流不允许")
            return None
        if not getattr(settings, "GLM_API_KEY", None):
            return None
        try:
            from zhipuai import ZhipuAI

            client = ZhipuAI(api_key=settings.GLM_API_KEY)
            resp = client.chat.completions.create(
                model=getattr(settings, "GLM_MODEL", "glm-4-flash"),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你是资产管理运维助手。基于给定的对账事实撰写简报，要求："
                            "1) 只使用给定事实，不得推测未提供的信息；"
                            "2) 如数据可信度为降级，开头必须先提示结果可能不全；"
                            "3) 按影子资产、疑似下线、信息不一致分组，各给出可执行建议；"
                            "4) 中文，200-350 字，不用 Markdown 标题，可用短横线列表。"
                        ),
                    },
                    {"role": "user", "content": facts},
                ],
                temperature=0.3,
                max_tokens=700,
            )
            text = (resp.choices[0].message.content or "").strip()
            ai_budget.record_success()
            return text or None
        except Exception as exc:  # noqa: BLE001 — AI 失败绝不能影响对账结论的可用性
            ai_budget.record_failure()
            logger.warning("对账报告 GLM 调用失败，降级模板: %s", exc)
            return None

    def _template_report(self, summary: dict, rows: list) -> str:
        """不依赖 LLM 的兜底文案。事实与 AI 版完全一致，只是不那么"顺口"。"""
        by_type = summary.get("by_type") or {}
        fr = summary.get("freshness") or {}
        parts: list[str] = []

        if fr.get("degraded"):
            reasons = []
            if not fr.get("wazuh_reachable"):
                reasons.append("Wazuh 不可达")
            if fr.get("sync_stale"):
                reasons.append(f"台账同步不新鲜（最近成功：{fr.get('last_sync_at') or '无记录'}）")
            if fr.get("unhealthy_sources"):
                reasons.append(f"{len(fr['unhealthy_sources'])} 个数据源异常")
            if fr.get("dead_letter_pending"):
                reasons.append(f"{fr['dead_letter_pending']} 条同步死信待处理")
            parts.append("⚠️ 数据可信度降级（" + "；".join(reasons) + "），以下结论可能不全。")

        total = summary.get("diff_total") or 0
        if total == 0:
            parts.append("本次对账未发现台账与实际网络的差异。")
            return " ".join(parts)

        seg = []
        if by_type.get(TYPE_SHADOW):
            seg.append(f"{by_type[TYPE_SHADOW]} 台影子资产（Wazuh 有 Agent、台账缺失）")
        if by_type.get(TYPE_OFFLINE):
            seg.append(f"{by_type[TYPE_OFFLINE]} 台疑似下线")
        if by_type.get(TYPE_MISMATCH):
            seg.append(f"{by_type[TYPE_MISMATCH]} 台信息不一致")
        parts.append(f"本次对账共发现 {total} 项差异：" + "、".join(seg) + "。")

        for r in rows[:5]:
            d = r.details or {}
            if r.reconciliation_type == TYPE_SHADOW:
                ag = d.get("agent") or {}
                parts.append(
                    f"影子资产 {ag.get('ip')}（{ag.get('name')}，{ag.get('os_name') or '系统未知'}）"
                    f"建议确认后补录台账。"
                )
            elif r.reconciliation_type == TYPE_OFFLINE:
                led = d.get("ledger") or {}
                if d.get("disconnected_days") is not None:
                    parts.append(
                        f"{led.get('asset_ip')} 已断开 {d['disconnected_days']} 天，可能是已退役设备。"
                    )
                else:
                    parts.append(f"{led.get('asset_ip')} 在 Wazuh 中已无对应 Agent，请确认是否退役。")
            else:
                led = d.get("ledger") or {}
                fields = "、".join(x.get("label", "") for x in (d.get("diffs") or []))
                parts.append(f"{led.get('asset_ip') or led.get('name')} 的 {fields} 与实际不符，建议核对。")
        return " ".join(parts)
