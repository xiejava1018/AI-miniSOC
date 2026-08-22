"""
自然语言资产查询服务（PRD F2.1，L1 + L2）

L1 范围：单表可表达的筛选/统计查询（意图识别 + 参数提取 + 映射资产查询）。
L2 范围：跨表/时间窗/跨源/分组统计 —— LLM 只选模板填参数，
执行层写死在 services/query_templates.py（零 LLM 参与，不生成 SQL）。

【单入口路由】PRD 明确要求 POST /assets/ask 一个端点自动路由：
    一次 LLM 调用同时判定「走 L1 还是 L2 哪个模板」，而不是先问一次 L1
    不行再问一次 L2（那样每个复合查询都要花两次 token，与§4.4 成本可控冲突）。

降级行为（§八-C）：GLM 不可用 → 提示“AI 服务暂不可用”并引导常规筛选器，不猜参数。
查询历史：复用 soc_chat_sessions（model_name='asset-query-l1' 区分）+ soc_chat_messages。
"""
import json
import logging
import re
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models import Asset
from app.models.chat import ChatSession, ChatMessage
from app.services.ai_budget import ai_budget

logger = logging.getLogger(__name__)

QUERY_SESSION_MODEL = "asset-query-l1"
MAX_RESULTS = 50
SUMMARY_RESULT_LIMIT = 30

# L1 支持的参数（PRD F2.1 Prompt 定义）；超出范围 → unsupported
SUPPORTED_ASSET_TYPES = {"server", "workstation", "iot", "network_device", "cloud", "other"}
SUPPORTED_CRITICALITY = {"critical", "high", "medium", "low"}

INTENT_PROMPT_TEMPLATE = """你是 IT 资产管理助手。用户会用中文提问关于资产的问题。
你的任务是把问题路由到两层能力之一，并提取参数。

【L1 — 单表筛选/统计】能用下列参数直接表达的问题走 L1：
   - asset_type: server/workstation/iot/network_device/cloud/other
   - os_name: 操作系统名（如 windows/ubuntu/centos）
   - criticality: critical/high/medium/low
   - asset_status: online/offline
   - network_segment: 网段或位置关键词（如 3F、机房）
   - owner: 负责人
   - keywords: 其他关键词（资产名/IP/描述）
   L1 意图：filter（筛选）/ stats（按维度统计，额外输出 stats_dimension）/ detail（单个详情）

【L2 — 复合查询】需要跨表（端口）/时间窗（掉线）/跨源（告警）/分组统计的问题走 L2，
从下列模板中选一个，并按其参数声明填值（参数名必须一字不差）：
{templates}

【路由优先级】
- 问题提到具体端口号、端口名（SSH/RDP/远程桌面）→ L2 port_open
- 问题问掉线/失联/多久没上线 → L2 offline_since
- 问题问某台资产的告警 → L2 asset_recent_alerts
- 问题是「按/每个…统计数量」且维度在 stats_group_by 的白名单内 → L2 stats_group_by
- 其余能用 L1 参数表达的 → L1
- 两层都表达不了（补丁/漏洞状态、多条件叠加、网络拓扑）→ unsupported

【严格要求】
1. 只提取用户明确表达的参数，不要编造；不确定就用 unsupported
2. 选了 L2 就必须给 template_id，且参数名取自上面模板声明
3. 只输出 JSON，不要任何其他文字。格式二选一：
   L1: {{"level": "L1", "intent": "filter", "params": {{...}}}}
   L2: {{"level": "L2", "template_id": "port_open", "params": {{"port": 3389}}}}
   无法处理: {{"level": "L1", "intent": "unsupported"}}

{context}用户问题: {question}"""

UNSUPPORTED_EXAMPLES = (
    "我目前支持这类问题：\n"
    "· “有哪些 Windows 服务器？”\n"
    "· “重要性为 critical 的资产有哪些？”\n"
    "· “3F 网段有哪些资产？”\n"
    "· “哪些资产开放了 3389 端口？”\n"
    "· “掉线超过 7 天的设备有哪些？”\n"
    "· “192.168.0.30 最近有什么告警？”\n"
    "· “按操作系统统计资产数量”\n"
    "暂不支持：补丁/漏洞状态（无数据源）、多条件叠加的复合查询、网络拓扑关系。"
)

_STATUS_MAP = {
    "online": ["online", "在线", "up"],
    "offline": ["offline", "离线", "down"],
}


def _extract_json(text: str) -> Optional[dict]:
    """从 GLM 回复中提取第一个 JSON 对象。"""
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        return None


class AssetQueryService:
    """L1 自然语言查询：GLM 意图识别 → 资产查询 → GLM 摘要（全程预算限流 + 降级）"""

    def __init__(self, db: Session):
        self.db = db

    # ---------- GLM 意图识别 ----------

    def _parse_intent(self, question: str, context: str = "") -> dict:
        """一次 LLM 调用同时完成 L1/L2 路由 + 参数提取。

        返回 {level, intent?, template_id?, params, stats_dimension?}；
        GLM 不可用抛 RuntimeError。

        模板清单从 configs/query_templates.yaml 动态渲染进 Prompt ——
        新增模板只改 YAML + 写一个执行器，本函数不用动。
        """
        if not ai_budget.allow():
            raise RuntimeError("budget")
        try:
            from zhipuai import ZhipuAI
            from app.core.config import settings
            from app.services.query_templates import template_catalog_for_prompt
            client = ZhipuAI(api_key=settings.GLM_API_KEY)
            prompt = INTENT_PROMPT_TEMPLATE.format(
                templates=template_catalog_for_prompt(),
                context=f"此前对话上下文（可继承其中的筛选条件）：{context}\n" if context else "",
                question=question,
            )
            resp = client.chat.completions.create(
                model=settings.GLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            ai_budget.record_success()
            parsed = _extract_json(resp.choices[0].message.content or "")
            if not parsed:
                return {"level": "L1", "intent": "unsupported", "params": {}}
            # 兼容：LLM 可能只给 template_id 而忘了 level，反之也可能
            if parsed.get("template_id") and not parsed.get("level"):
                parsed["level"] = "L2"
            if not parsed.get("level"):
                parsed["level"] = "L1"
            if parsed["level"] == "L1" and "intent" not in parsed:
                parsed["intent"] = "unsupported"
            return parsed
        except RuntimeError:
            raise
        except Exception as e:
            ai_budget.record_failure()
            raise RuntimeError(f"glm_error: {e}") from e

    # ---------- 参数映射 → 查询 ----------

    def _apply_filters(self, q, params: dict):
        p = params or {}
        at = (p.get("asset_type") or "").lower()
        if at in SUPPORTED_ASSET_TYPES:
            q = q.filter(Asset.asset_type == at)
        os_name = (p.get("os_name") or "").strip()
        if os_name:
            q = q.filter(Asset.os_name.ilike(f"%{os_name}%"))
        crit = (p.get("criticality") or "").lower()
        if crit in SUPPORTED_CRITICALITY:
            q = q.filter(Asset.criticality == crit)
        status = (p.get("asset_status") or "").lower()
        for key, variants in _STATUS_MAP.items():
            if status in variants:
                q = q.filter(Asset.asset_status.in_(variants))
                break
        seg = (p.get("network_segment") or "").strip()
        if seg:
            q = q.filter(or_(
                Asset.network_segment.ilike(f"%{seg}%"),
                Asset.network_zone.ilike(f"%{seg}%"),
            ))
        owner = (p.get("owner") or "").strip()
        if owner:
            q = q.filter(Asset.owner.ilike(f"%{owner}%"))
        kw = (p.get("keywords") or "").strip()
        if kw:
            q = q.filter(or_(
                Asset.name.ilike(f"%{kw}%"),
                Asset.asset_ip.ilike(f"%{kw}%"),
                Asset.asset_description.ilike(f"%{kw}%"),
            ))
        return q

    @staticmethod
    def _asset_brief(a: Asset) -> dict:
        return {
            "id": str(a.id),
            "name": a.name,
            "ip": a.asset_ip,
            "asset_type": a.asset_type,
            "os_name": a.os_name,
            "os_version": a.os_version,
            "criticality": a.criticality,
            "asset_status": a.asset_status,
            "owner": a.owner,
            "network_segment": a.network_segment,
            "risk_score": a.risk_score,
        }

    # ---------- 摘要 ----------

    def _summarize(self, question: str, results: list, stats: Optional[dict]) -> str:
        if stats is not None:
            lines = "；".join(f"{k}：{v} 台" for k, v in stats.items())
            return f"统计结果（共 {sum(stats.values())} 台）：{lines}"
        n = len(results)
        if n == 0:
            return "没有找到符合条件的资产。可放宽条件或检查关键词。"
        # 模板摘要（零成本，始终可用）
        top = "、".join(f"{r['name'] or r['ip']}" for r in results[:5])
        template = f"找到 {n} 台符合条件的资产：{top}{' 等' if n > 5 else ''}。"
        if n > SUMMARY_RESULT_LIMIT:
            return template
        if not ai_budget.allow():
            return template + "（AI 摘要服务暂不可用）"
        try:
            from zhipuai import ZhipuAI
            from app.core.config import settings
            client = ZhipuAI(api_key=settings.GLM_API_KEY)
            rows = "\n".join(
                f"- {r['name'] or r['ip']} ({r['ip']}, {r['os_name'] or '未知OS'}, {r['criticality']}, {r['asset_status'] or '未知状态'})"
                for r in results[:20]
            )
            prompt = (
                f"用户问题：{question}\n查询结果（{n} 台）：\n{rows}\n"
                "用一两句中文总结结果（总数 + 值得注意的点，如高危系统版本、离线设备），不超过60字，不要寒暄。"
            )
            resp = client.chat.completions.create(
                model=settings.GLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            ai_budget.record_success()
            text = (resp.choices[0].message.content or "").strip()
            return text or template
        except Exception as e:
            ai_budget.record_failure()
            logger.warning("查询摘要 GLM 失败，用模板: %s", e)
            return template

    # ---------- 主入口 ----------

    def ask(self, question: str, user_id: Optional[int] = None, session_id: Optional[str] = None) -> dict:
        question = (question or "").strip()
        if not question:
            return {"level": "L1", "intent": "error", "message": "问题不能为空"}

        # 会话上下文（最近 2 轮 user 消息，轻量多轮支持）
        context = ""
        session = None
        if session_id:
            try:
                import uuid as _uuid
                session = (
                    self.db.query(ChatSession)
                    .filter(ChatSession.id == _uuid.UUID(session_id), ChatSession.user_id == user_id)
                    .first()
                )
                if session:
                    prev = (
                        self.db.query(ChatMessage)
                        .filter(ChatMessage.session_id == session.id, ChatMessage.role == "user")
                        .order_by(ChatMessage.created_at.desc())
                        .limit(2)
                        .all()
                    )
                    context = "；".join(m.content for m in reversed(prev))
            except Exception:
                session = None

        # 1) 意图识别（预算限流；不可用 → 诚实降级）
        try:
            parsed = self._parse_intent(question, context)
        except RuntimeError as e:
            msg = "AI 服务暂不可用，请稍后重试，或使用资产列表页的筛选器。"
            if "budget" in str(e):
                msg = "AI 查询已达调用限额（今日配额或限流），请稍后重试，或使用资产列表页筛选器。"
            return {"level": "L1", "intent": "unavailable", "message": msg}

        intent = parsed.get("intent", "unsupported")
        params = parsed.get("params") or {}
        level = parsed.get("level") or "L1"

        # 1.5) L2 分支：模板执行（此后全程不再碰 LLM，除了最后的摘要）
        if level == "L2":
            return self._run_l2(question, parsed, user_id, session)

        if intent == "unsupported":
            return self._persist(question, {"level": "L1", "intent": "unsupported",
                                            "params": {}, "assets": [], "summary": UNSUPPORTED_EXAMPLES},
                                 user_id, session)

        # 2) 执行查询
        try:
            q = self.db.query(Asset)
            q = self._apply_filters(q, params)
            if intent == "stats":
                # 统计类统一委派给 L2 stats_group_by 模板——避免两层各写一份分组逻辑。
                #
                # 实测过的真问题：「按操作系统统计」首问路由到 L2（带「49 台字段为空」
                # 覆盖率警告），作为追问时却路由到 L1（无覆盖率警告）——
                # 同一个问题两种诚实度。覆盖率披露不能取决于 LLM 路由到哪层。
                dim = parsed.get("stats_dimension") or params.get("stats_dimension") or "asset_type"
                from app.services import query_templates as qt
                try:
                    qt.validate("stats_group_by", {"dimension": dim})
                except qt.TemplateError:
                    dim = "asset_type"  # 维度不在白名单则回退到默认
                return self._run_l2(
                    question,
                    {"template_id": "stats_group_by", "params": {"dimension": dim}},
                    user_id, session,
                )

            assets = q.order_by(Asset.risk_score.desc().nullslast(), Asset.updated_at.desc()).limit(MAX_RESULTS).all()
            results = [self._asset_brief(a) for a in assets]
            result = {
                "level": "L1", "intent": intent, "params": params,
                "total": len(results), "assets": results, "summary": "",
            }
            result["summary"] = self._summarize(question, results, None)
            return self._persist(question, result, user_id, session)
        except Exception as e:
            logger.error("L1 查询执行失败: %s", e)
            return {"level": "L1", "intent": "error", "message": "查询执行失败，请稍后重试"}

    # ---------- L2 模板执行 ----------

    def _run_l2(self, question: str, parsed: dict, user_id: Optional[int],
                session: Optional[ChatSession]) -> dict:
        """执行 L2 模板查询。

        参数校验失败时**不静默降级到 L1**（那会用错的口径给出一个看似合理的答案），
        而是如实告知哪个参数不对 + 可用示例。
        """
        from app.services import query_templates as qt

        template_id = parsed.get("template_id") or ""
        params = parsed.get("params") or {}
        try:
            out = qt.execute(self.db, template_id, params)
        except qt.TemplateError as e:
            return self._persist(question, {
                "level": "L2", "intent": "invalid_params",
                "template_id": template_id, "params": params,
                "assets": [], "summary": f"无法执行查询：{e}\n\n{qt.unsupported_hint()}",
            }, user_id, session)
        except Exception as e:
            logger.error("L2 模板执行失败 template=%s params=%s: %s", template_id, params, e)
            return {"level": "L2", "intent": "error", "message": "查询执行失败，请稍后重试"}

        result = {
            "level": "L2",
            "intent": "template",
            "template_id": out["template_id"],
            "template_name": out["template_name"],
            "params": out["params"],
            "templates_version": out["templates_version"],
            "assets": out.get("assets") or [],
            "total": out.get("total", len(out.get("assets") or [])),
            "notes": out.get("notes") or [],
            "summary": "",
        }
        # 模板特有字段原样透传给前端
        for k in ("stats", "stats_dimension", "coverage", "alerts", "data_degraded"):
            if k in out:
                result[k] = out[k]
        result["summary"] = self._summarize_l2(question, result)
        return self._persist(question, result, user_id, session)

    def _summarize_l2(self, question: str, result: dict) -> str:
        """L2 摘要：先拼零成本模板，再试 GLM 潦话化。

        notes（口径/覆盖率说明）永远由后端拼，**不交给 LLM 改写** ——
        数据覆盖率这种事实不能被潦话化掉。
        """
        tpl = result.get("template_id")
        stats = result.get("stats")
        alerts = result.get("alerts")
        assets = result.get("assets") or []

        if stats is not None:
            cov = result.get("coverage") or {}
            top = "、".join(f"{k} {v} 台" for k, v in list(stats.items())[:6])
            template = f"按 {result.get('stats_dimension')} 统计：{top or '无数据'}。"
            if cov.get("missing"):
                template += f"（{cov['missing']}/{cov.get('total')} 台该字段为空，未计入）"
        elif alerts is not None:
            b = alerts.get("buckets") or {}
            a0 = assets[0] if assets else {}
            template = (
                f"{a0.get('name') or a0.get('ip')} 近 {alerts.get('days')} 天共 {b.get('total', 0)} 条告警："
                f"critical {b.get('critical', 0)}、high {b.get('high', 0)}、"
                f"medium {b.get('medium', 0)}、low {b.get('low', 0)}。"
            )
        elif result.get("data_degraded"):
            template = "告警数据源不可用，无法给出告警统计（不代表无告警）。"
        else:
            n = len(assets)
            if n == 0:
                template = "没有找到符合条件的资产。"
            else:
                top = "、".join(f"{r.get('name') or r.get('ip')}" for r in assets[:5])
                template = f"找到 {n} 台：{top}{' 等' if n > 5 else ''}。"

        if not ai_budget.allow():
            return template
        try:
            from zhipuai import ZhipuAI
            from app.core.config import settings
            client = ZhipuAI(api_key=settings.GLM_API_KEY)
            # 字段名必须无歧义：曾经传模糊的 "total"（实为资产数）导致 GLM 把
            # 「匹配到 1 台资产」说成「有 1 个告警」，后半句又说 635 个高危——
            # 自相矛盾。歧义字段名本身就是幻觉源。
            facts = {
                "template": tpl,
                "params": result.get("params"),
                "matched_asset_count": len(assets),
                "assets": [
                    {"name": a.get("name"), "ip": a.get("ip"), "criticality": a.get("criticality"),
                     "os": a.get("os_name"), "offline_days": a.get("offline_days")}
                    for a in assets[:15]
                ],
            }
            if stats is not None:
                facts["asset_count_by_dimension"] = stats
                facts["data_coverage"] = result.get("coverage")
            if alerts is not None:
                b = alerts.get("buckets") or {}
                facts["alert_counts"] = {
                    "window_days": alerts.get("days") or b.get("window_days"),
                    "alert_total": b.get("total"),
                    "critical": b.get("critical"),
                    "high": b.get("high"),
                    "medium": b.get("medium"),
                    "low": b.get("low"),
                }
            prompt = (
                f"用户问题：{question}\n"
                f"查询事实（JSON）：{json.dumps(facts, ensure_ascii=False, default=str)[:2500]}\n"
                "用一到两句中文回答用户的问题（总数 + 值得注意的点），不超过 80 字。\n"
                "硬约束：\n"
                "1) 只能用上述事实，不得推测、不得编造数字；\n"
                "2) matched_asset_count 是「资产台数」，alert_counts.alert_total 是「告警条数」，"
                "两者是不同的量，绝不得混用或互相替代；\n"
                "3) 不要寒暄，不要重复参数原文。"
            )
            resp = client.chat.completions.create(
                model=settings.GLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            ai_budget.record_success()
            text = (resp.choices[0].message.content or "").strip()
            return text or template
        except Exception as e:
            ai_budget.record_failure()
            logger.warning("L2 摘要 GLM 失败，用模板: %s", e)
            return template

    # ---------- 历史持久化 ----------

    def _persist(self, question: str, result: dict, user_id: Optional[int], session: Optional[ChatSession]) -> dict:
        try:
            if session is None:
                session = ChatSession(
                    user_id=user_id, title=question[:30],
                    model_name=QUERY_SESSION_MODEL,
                )
                self.db.add(session)
                self.db.flush()
            else:
                from datetime import datetime as _dt, timezone as _tz
                session.updated_at = _dt.now(_tz.utc)
            self.db.add_all([
                ChatMessage(session_id=session.id, role="user", content=question),
                ChatMessage(session_id=session.id, role="assistant",
                            content=json.dumps(result, ensure_ascii=False, default=str)[:8000]),
            ])
            self.db.commit()
            result["session_id"] = str(session.id)
        except Exception as e:
            self.db.rollback()
            logger.warning("查询历史落库失败（不影响结果返回）: %s", e)
        return result

    def history(self, user_id: Optional[int], limit: int = 20) -> list:
        """当前用户的 L1 查询会话历史（供前端重放）。"""
        q = self.db.query(ChatSession).filter(ChatSession.model_name == QUERY_SESSION_MODEL)
        if user_id is not None:
            q = q.filter(ChatSession.user_id == user_id)
        sessions = q.order_by(ChatSession.updated_at.desc()).limit(limit).all()
        out = []
        for s in sessions:
            last = (
                self.db.query(ChatMessage)
                .filter(ChatMessage.session_id == s.id, ChatMessage.role == "assistant")
                .order_by(ChatMessage.created_at.desc())
                .first()
            )
            out.append({
                "session_id": str(s.id),
                "title": s.title,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                "last_answer": (last.content[:200] + "…") if last and len(last.content) > 200 else (last.content if last else None),
            })
        return out
