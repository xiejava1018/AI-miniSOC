"""
合规 AI 解读层（PRD F3.3 双层架构的 AI 层）

【职责边界 —— 与判定层严格隔离】
  输入：compliance.py 已判定为 fail 的 finding（判定结论已成事实）
  输出：整改建议文本，写入 finding.ai_remediation
  禁止：改变 status、生成新 finding、判断「是否合规」

  换句话说：AI 在这里回答「为什么危险、怎么修」，绝不回答「是否达标」。
  即使 GLM 返回「其实这个没问题」，判定结果也不会变——它只是 remediation 文本。

【不给 unknown 生成解读】
  unknown 意味着数据缺失，正确动作是补数据（部署 Agent / 补端口扫描），
  让 AI 对着空数据写建议只会生成看似合理的空话。

【降级】
  GLM 不可用 / 预算超限 → 回落规则化模板（规则自带 remediation_hint），
  标记 ai_model='fallback:rule'，前端据此不打「AI 生成」角标。
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Asset, ComplianceFinding
from app.services.ai_budget import ai_budget
from app.services.compliance import load_ruleset

logger = logging.getLogger(__name__)

PROMPT_VERSION = "compliance-remediation@v1"

# --- 时间预算 ---------------------------------------------------------------
# zhipuai 客户端默认 read timeout=300s、max_retries=3 —— 单条 finding 最坏可挂
# 900s+，而前端 axios 只等 180s。结果就是「前端报网络错误、后端还在跑、跑完
# 又成功了」。这里把单次调用钉死，让整批耗时可预期。
GLM_CALL_TIMEOUT_SECONDS = 30.0   # 实测 p50 约 9s，30s 给到 3 倍余量
GLM_MAX_RETRIES = 1

# 单条最坏耗时（首次 + 重试全超时）
WORST_SINGLE_ITEM_SECONDS = GLM_CALL_TIMEOUT_SECONDS * (1 + GLM_MAX_RETRIES)

# 单次 HTTP 请求的软截止：到点就停止领新任务并把 remaining 报给调用方。
#
# 【不可破的不变式】截止检查在每条开始前，所以最后一条可能刚好在截止前
#   起跑，单次请求最坏耗时 = DEADLINE + WORST_SINGLE_ITEM，不是 DEADLINE。
#   必须满足：DEADLINE + WORST_SINGLE_ITEM < 前端 axios timeout（现 180s）
#   当前：90 + 60 = 150s < 180s，留 30s 给响应与渲染。
#   改大任何一个常量前先重算这个不等式，否则超时 bug 会原样复现。
DEFAULT_DEADLINE_SECONDS = 90.0


class ComplianceAIService:
    """合规问题 AI 解读（只读判定结果）"""

    def __init__(self, db: Session):
        self.db = db
        self._rules_by_id = {r["id"]: r for r in load_ruleset()["rules"]}

    # ------------------------------------------------------------------

    def interpret_run(
        self,
        run_id,
        limit: int = 10,
        force: bool = False,
        deadline_seconds: float = DEFAULT_DEADLINE_SECONDS,
    ) -> dict:
        """为一次巡检的 fail 项批量生成整改建议（按严重度优先，限量控成本）。

        单次调用受 deadline_seconds 约束：到点即停止领新任务，已完成的部分
        逐条落库，未处理的条数通过 remaining 返回。调用方据此续跑下一批。
        """
        q = (self.db.query(ComplianceFinding)
             .filter(ComplianceFinding.run_id == run_id,
                     ComplianceFinding.status == "fail"))
        if not force:
            q = q.filter(ComplianceFinding.ai_remediation.is_(None))
        rows = q.all()
        sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        rows.sort(key=lambda f: (sev_order.get(f.severity or "medium", 9), f.rule_id))
        pending_total = len(rows)
        rows = rows[:max(1, min(limit, 50))]

        stats = {
            "candidates": len(rows),
            "generated": 0,
            "fallback": 0,
            "errors": 0,
            # 本批之外仍待生成的条数（供调用方决定是否续跑）
            "remaining": 0,
            "stopped_by_deadline": False,
        }
        started = time.monotonic()
        for f in rows:
            # 软截止：宁可少做一条并如实上报 remaining，也不要让请求超出前端等待
            # 上限——超时的请求会让用户以为「失败了」，而后端其实还在写数据。
            if time.monotonic() - started >= deadline_seconds:
                stats["stopped_by_deadline"] = True
                break
            try:
                text, model = self._remediation(f)
                f.ai_remediation = text
                f.ai_model = model
                f.ai_prompt_version = PROMPT_VERSION
                f.ai_generated_at = datetime.now(timezone.utc)
                if model.startswith("fallback"):
                    stats["fallback"] += 1
                else:
                    stats["generated"] += 1
                # 逐条 commit：客户端断开（超时/关页面）时已生成的建议不丢，
                # 也不会因为最后一条异常回滚掉前面几十秒的 token 花费。
                self.db.commit()
            except Exception as e:  # noqa: BLE001
                logger.warning("合规解读失败 %s: %s", f.rule_id, e)
                self.db.rollback()
                stats["errors"] += 1

        stats["remaining"] = max(0, pending_total - stats["generated"] - stats["fallback"])
        return stats

    # ------------------------------------------------------------------

    def _remediation(self, f: ComplianceFinding) -> tuple[str, str]:
        rule = self._rules_by_id.get(f.rule_id) or {}
        glm = self._glm_remediation(f, rule)
        if glm:
            return glm, "glm"
        return self._template(f, rule), "fallback:rule"

    def _template(self, f: ComplianceFinding, rule: dict) -> str:
        """规则化降级文案：全部信息来自规则库与判定 evidence，无编造。"""
        parts = [
            f"【判定依据】{f.reason}",
            f"【规则】{f.rule_id} v{f.rule_version} {f.rule_title}",
        ]
        if rule.get("baseline"):
            parts.append(f"【对照基线】{rule['baseline']}")
        if rule.get("rationale"):
            parts.append(f"【风险说明】{rule['rationale']}")
        if rule.get("remediation_hint"):
            parts.append(f"【整改方向】{rule['remediation_hint']}")
        parts.append("（AI 解读不可用，以上为规则库预置说明）")
        return "\n".join(parts)

    def _glm_remediation(self, f: ComplianceFinding, rule: dict) -> Optional[str]:
        if not ai_budget.allow():
            return None
        asset = self.db.query(Asset).filter(Asset.id == f.asset_id).first()
        if not asset:
            return None
        try:
            from zhipuai import ZhipuAI
            from app.core.config import settings
            client = ZhipuAI(
                api_key=settings.GLM_API_KEY,
                timeout=GLM_CALL_TIMEOUT_SECONDS,
                max_retries=GLM_MAX_RETRIES,
            )

            os_label = f"{asset.os_name or ''} {asset.os_version or ''}".strip() or "未知"
            prompt = (
                "你是等保合规整改顾问。下面是一条【已由规则引擎确定为不达标】的合规问题，"
                "判定结论不可更改，你的任务只是给出整改建议。\n"
                "要求：\n"
                "1) 输出 3-5 条可执行步骤，每条一行，以「- 」开头；\n"
                "2) 必须在开头一句说明该问题的实际风险（结合资产用途与暴露面）；\n"
                "3) 末尾用一行给出验证方式（如何确认整改生效）；\n"
                "4) 不要质疑判定结论，不要输出「可能不算违规」之类的话；\n"
                "5) 不确定的信息不要编造具体命令参数，用占位符说明；\n"
                "6) 纯文本，不要 markdown 标题，不要客套话。\n\n"
                f"【规则】{f.rule_id} v{f.rule_version}：{f.rule_title}\n"
                f"【对照基线】{rule.get('baseline', '未标注')}\n"
                f"【规则意图】{rule.get('rationale', '')}\n"
                f"【预置整改方向】{rule.get('remediation_hint', '')}\n"
                f"【判定依据】{f.reason}\n"
                f"【判定证据】{f.evidence}\n"
                f"【资产】{asset.name or asset.asset_ip}（IP {asset.asset_ip}，"
                f"类型 {asset.asset_type}，重要度 {asset.criticality}，"
                f"暴露面 {asset.exposure_level}，系统 {os_label}）"
            )
            resp = client.chat.completions.create(
                model=settings.GLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            ai_budget.record_success()
            text = (resp.choices[0].message.content or "").strip()
            if len(text) < 20:
                return None
            # 溯源：AI 文本前置规则 ID，审计时可直接对照规则库版本
            return f"[依据 {f.rule_id} v{f.rule_version}]\n{text}"
        except Exception as e:  # noqa: BLE001
            ai_budget.record_failure()
            logger.warning("合规解读 GLM 调用失败，走模板降级: %s", e)
            return None
