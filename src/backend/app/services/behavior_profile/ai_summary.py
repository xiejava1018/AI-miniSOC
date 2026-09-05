"""画像 AI 解读（Phase 3，方案 Phase 3 / PRD AI 增强）

GLM 把画像五层事实讲成"这个人/这台设备在干什么、有没有异常"。
降级路径（与 impact_analysis/reconcile_ai 同款）：
  - ai_budget.allow() / GLM Key / 调用失败 → _template_summary()

Prompt 硬约束（F2.2/F3.1 实测教训）：
  1. 三字段纯文本，禁 JSON 数组/嵌套 dict（_flatten_to_text 兜底）
  2. 禁具体日期，只写相对表述（GLM 会编造 "2023-04-01"）
  3. degraded 时 summary 开头必须声明降级并说明原因，不得一笔带过
  4. 只输出信号不定性（§6 合规）：不写"某人违规"，写"存在异常信号，需人工复核"
"""

import logging
from typing import Any, Optional

from app.core.config import settings
from app.services.ai_budget import ai_budget

logger = logging.getLogger(__name__)

PROMPT_VERSION = "behavior-profile-v1"


def _flatten_to_text(v: Any, depth: int = 0) -> str:
    """GLM 可能返回 dict/list 而非纯文本——递归扁平成可读中文（F3.1 同款）。"""
    indent = "  " * depth
    if v is None:
        return ""
    if isinstance(v, dict):
        lines = []
        for k, val in v.items():
            sub = _flatten_to_text(val, depth + 1)
            lines.append(f"{indent}- {k}: {sub}".rstrip())
        return "\n".join(lines)
    if isinstance(v, (list, tuple)):
        return "\n".join(
            f"{indent}- {_flatten_to_text(item, depth + 1).lstrip('- ')}"
            for item in v
        )
    return f"{indent}{v}" if depth else str(v)


def _build_facts(profile: dict) -> dict:
    """从 get_profile 输出抽 LLM 友好事实。字段名自成量纲（防幻觉，F2.1 教训）。"""
    days_rows = profile.get("daily") or []
    ok_rows = [r for r in days_rows if r.get("status") == "ok"]
    gap_days = sum(1 for r in days_rows if r.get("status") == "gap")
    by_hour = profile.get("by_hour") or [0] * 24
    total = profile.get("total") or 0
    asset = profile.get("asset") or {}
    night = sum(by_hour[:6])
    layer = profile.get("layer_visit") or {}

    facts = {
        "target_ip": profile.get("ip"),
        "hostname": asset.get("name") or (days_rows[0].get("hostname") if days_rows else None),
        "asset_type": asset.get("asset_type"),
        "owner": asset.get("owner") or "未登记",
        "window_days": profile.get("days"),
        "snapshots_ok": len(ok_rows),
        "snapshots_gap": gap_days,
        "total_visits": total,
        "traffic_type": profile.get("traffic_type"),
        "confidence": profile.get("confidence"),
        "night_00_06_ratio_pct": round(night / total * 100, 1) if total else 0,
        "act_layer_ratio_pct": layer.get("ACT", 0),
        "sys_layer_ratio_pct": layer.get("SYS", 0),
        "ad_layer_ratio_pct": layer.get("AD", 0),
        "top_categories_pct": profile.get("cat_share") or {},
        "top_domains": [
            f"{d['domain']}({d['visits']}次,{d['share']}%)"
            for d in (profile.get("top_domains") or [])[:10]
        ],
        "rule_tags": [
            f"{t.get('name')}({t.get('evidence','')})" for t in (profile.get("tags") or [])
        ],
        "degrade_reasons": [],
    }
    if gap_days:
        facts["degrade_reasons"].append(f"{gap_days} 天快照缺失（超出 Loki 保留窗口）")
    if (profile.get("confidence") or 0) < 60:
        facts["degrade_reasons"].append(f"快照置信度仅 {profile.get('confidence')}/100（数据量少或查询截断）")
    if profile.get("traffic_type") == "machine":
        facts["degrade_reasons"].append("机器流量为主，'作息/兴趣'类结论对人类行为不适用")
    facts["data_degraded"] = bool(facts["degrade_reasons"])
    return facts


class ProfileAIService:
    """画像 AI 解读：GLM 摘要 + 异常解读，带诚实降级。"""

    def summarize(self, profile: dict) -> dict:
        facts = _build_facts(profile)
        text, source = self._glm_summary(facts)
        if text is None:
            text = self._template_summary(facts)
            source = "template"
        return {
            "ip": profile.get("ip"),
            "source": source,                       # glm / template
            "prompt_version": PROMPT_VERSION,
            "summary": text.get("summary", ""),
            "anomaly_interpretation": text.get("anomaly_interpretation", ""),
            "recommendations": text.get("recommendations", ""),
            "data_degraded": facts["data_degraded"],
            "degrade_reasons": facts["degrade_reasons"],
            "disclaimer": "画像仅输出信号，不定性；结论须经人工复核（仅用于安全审计）",
        }

    # ---------- GLM ----------

    def _glm_summary(self, facts: dict) -> tuple[Optional[dict], str]:
        if not getattr(settings, "GLM_API_KEY", None):
            return None, "template"
        if not ai_budget.allow():
            logger.info("画像 AI：预算熔断中，走模板")
            return None, "template"
        try:
            from zhipuai import ZhipuAI

            prompt = self._prompt(facts)
            client = ZhipuAI(api_key=settings.GLM_API_KEY)
            resp = client.chat.completions.create(
                model=getattr(settings, "GLM_MODEL", "glm-4-flash"),
                messages=[
                    {"role": "system", "content": "你是企业内网安全审计助手，只基于给定事实输出，不编造。"},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
            )
            text = resp.choices[0].message.content
            ai_budget.record_success()
            parsed = self._parse_json(text)
            return parsed, "glm"
        except Exception as exc:
            ai_budget.record_failure()
            logger.warning("画像 AI GLM 调用失败，降级模板: %s", exc)
            return None, "template"

    def _prompt(self, facts: dict) -> str:
        import json as _json

        return (
            "以下是某台内网设备/IP 的行为画像事实（安全审计用途）。请输出 JSON 对象，"
            "仅含三个键：summary、anomaly_interpretation、recommendations。\n"
            "硬约束：\n"
            "1) 三个键的值必须是纯文本段落（recommendations 用换行分隔的要点，"
            "每行以 - 开头），不要 JSON 数组、不要嵌套对象、不要 Markdown 代码块；\n"
            "2) 严禁出现任何具体日期（如 2023-04-01），只允许相对表述（如 近7天、凌晨时段）；\n"
            "3) 若 facts.data_degraded 为 true，summary 必须以「数据可信度降级，结果可能不全。」开头，"
            "并紧接说明原因（引用 degrade_reasons），不得一笔带过；\n"
            "4) anomaly_interpretation 只描述「信号」，不定性到人（不写某人违规），"
            "并明确提示需人工复核；\n"
            "5) 只使用 facts 中的数字，不得推算 facts 里没有的量。\n\n"
            f"facts = {_json.dumps(facts, ensure_ascii=False, default=str)}"
        )

    @staticmethod
    def _parse_json(text: str) -> Optional[dict]:
        import json as _json
        import re as _re

        if not text:
            return None
        cleaned = _re.sub(r"```(?:json)?|```", "", text).strip()
        try:
            data = _json.loads(cleaned)
        except Exception:
            start, end = cleaned.find("{"), cleaned.rfind("}")
            if start < 0 or end <= start:
                return None
            try:
                data = _json.loads(cleaned[start:end + 1])
            except Exception:
                return None
        if not isinstance(data, dict):
            return None
        return {k: _flatten_to_text(data.get(k)) for k in
                ("summary", "anomaly_interpretation", "recommendations")}

    # ---------- 降级模板 ----------

    @staticmethod
    def _template_summary(facts: dict) -> dict:
        head = ""
        if facts["data_degraded"]:
            reasons = "；".join(facts["degrade_reasons"])
            head = f"数据可信度降级，结果可能不全。原因：{reasons}。\n"

        total = facts["total_visits"]
        tt = facts["traffic_type"]
        tt_desc = {"human": "人类行为", "machine": "机器流量（系统/协议心跳为主）",
                   "mixed": "人机混合流量"}.get(tt, tt)
        cats = "、".join(f"{k} {v}%" for k, v in list(facts["top_categories_pct"].items())[:3]) or "无主动行为分类"
        lines = [l for l in [
            head,
            f"近 {facts['window_days']} 天（有效快照 {facts['snapshots_ok']} 天），"
            f"累计访问 {total} 次，判定为{tt_desc}。",
            f"主要访问构成：{cats}。",
            f"凌晨 00-06 点占比 {facts['night_00_06_ratio_pct']}%。",
            "（规则引擎口径，非 AI 生成）",
        ] if l]

        anomaly = "；".join(facts["rule_tags"]) or "规则引擎未命中异常标签"
        recs = ["- 人工复核该画像与标签证据（画像仅输出信号，不定性）"]
        if facts["traffic_type"] == "machine":
            recs.append("- 机器流量主体：行为节律/兴趣分类不适用，关注暴露面与漏洞维度")
        if facts["snapshots_gap"]:
            recs.append(f"- 有 {facts['snapshots_gap']} 天数据缺失，趋势结论请谨慎使用")

        return {
            "summary": "\n".join(lines),
            "anomaly_interpretation": f"规则标签信号：{anomaly}（需人工复核）",
            "recommendations": "\n".join(recs),
        }
