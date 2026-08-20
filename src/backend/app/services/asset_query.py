"""
自然语言资产查询服务（PRD F2.1 L1，P3 MVP）

L1 范围：仅单表可表达的筛选/统计查询。
技术路线（PRD v1.2 修订）：意图识别 + 参数提取 + 映射资产查询 —— 不做 NL2SQL，
不硬塞复合查询（端口/时间趋势类问题 → intent=unsupported 诚实拒答，L2 模板方案后续迭代）。

降级行为（§八-C）：GLM 不可用 → 提示"AI 服务暂不可用"并引导常规筛选器，不猜参数。
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

你需要：
1. 判断查询意图：filter（筛选资产）/ stats（按维度统计数量）/ detail（单个资产详情）/ unsupported（无法用下述参数表达）
2. 提取查询参数（只提取用户明确表达的，不要编造）：
   - asset_type: server/workstation/iot/network_device/cloud/other
   - os_name: 操作系统名（如 windows/ubuntu/centos）
   - criticality: critical/high/medium/low
   - asset_status: online/offline
   - network_segment: 网段或位置关键词（如 3F、机房）
   - owner: 负责人
   - keywords: 其他关键词（资产名/IP/描述）
3. 若是统计类问题，额外输出 stats_dimension: os_name/asset_type/criticality 之一
4. 严格限制：问题涉及端口号、告警、漏洞、时间趋势、"没打补丁"等超出上述参数的内容时，intent 必须为 unsupported
5. 只输出 JSON，不要任何其他文字。格式：
{{"intent": "filter", "params": {{...}}}}
或 {{"intent": "unsupported"}}
或 {{"intent": "stats", "stats_dimension": "os_name", "params": {{...}}}}

{context}用户问题: {question}"""

UNSUPPORTED_EXAMPLES = (
    "我目前支持这类问题：\n"
    "· “有哪些 Windows 服务器？”\n"
    "· “重要性为 critical 的资产有哪些？”\n"
    "· “3F 网段有哪些资产？”\n"
    "· “负责人张三的资产”\n"
    "· “按操作系统统计资产数量”\n"
    "涉及端口、告警、漏洞、补丁状态的复合查询即将上线（L2），请先用列表页筛选器。"
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
        """返回 {intent, params, stats_dimension?}；GLM 不可用抛 RuntimeError。"""
        if not ai_budget.allow():
            raise RuntimeError("budget")
        try:
            from zhipuai import ZhipuAI
            from app.core.config import settings
            client = ZhipuAI(api_key=settings.GLM_API_KEY)
            prompt = INTENT_PROMPT_TEMPLATE.format(
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
            if not parsed or "intent" not in parsed:
                return {"intent": "unsupported", "params": {}}
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

        if intent == "unsupported":
            return self._persist(question, {"level": "L1", "intent": "unsupported",
                                            "params": {}, "assets": [], "summary": UNSUPPORTED_EXAMPLES},
                                 user_id, session)

        # 2) 执行查询
        try:
            q = self.db.query(Asset)
            q = self._apply_filters(q, params)
            if intent == "stats":
                from sqlalchemy import func
                dim = parsed.get("stats_dimension") or "asset_type"
                col = {"os_name": Asset.os_name, "asset_type": Asset.asset_type,
                       "criticality": Asset.criticality}.get(dim, Asset.asset_type)
                base = self._apply_filters(self.db.query(Asset), params)
                rows = base.with_entities(col, func.count(Asset.id)).group_by(col).all()
                stats_result = {str(k or "未知"): c for k, c in rows}
                stats_result = dict(sorted(stats_result.items(), key=lambda kv: -kv[1]))
                result = {
                    "level": "L1", "intent": "stats", "params": params,
                    "stats_dimension": dim, "stats": stats_result,
                    "assets": [], "summary": "",
                }
                result["summary"] = self._summarize(question, [], stats_result)
                return self._persist(question, result, user_id, session)

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
