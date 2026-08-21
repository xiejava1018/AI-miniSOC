"""
运维知识库服务（PRD F2.3，P3 W8）

三大能力：
1. 自动提取（auto_extract）：从已解决/关闭事件提取「故障→原因→解决方案」三元组。
   GLM 生成（预算限流），失败降级为 resolution_notes 模板整理（§八-C）；
   source_type+source_id 幂等去重（同一事件不重复提取）；
   confidence=70（PRD：AI 提取默认置信度）
2. 智能检索（search）：关键词召回 → GLM rerank（预算限流）；
   召回为空 → 诚实返回空（不编造）；GLM 不可用 → 召回顺序 + 提示
3. 老化管理：last_validated_at 超 12 个月自动 pending_review（列表懒触发，
   200 台规模知识量小，UPDATE 成本可忽略）；validate 刷新时间 + confidence=90
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.models import Incident
from app.models.knowledge import Knowledge
from app.services.ai_budget import ai_budget

logger = logging.getLogger(__name__)

STALE_MONTHS = 12
EXTRACT_BATCH_LIMIT = 20
SEARCH_RECALL_LIMIT = 10
VALID_CATEGORIES = {"troubleshooting", "configuration", "policy", "reference"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_out(k: Knowledge) -> dict:
    return {
        "id": str(k.id),
        "title": k.title,
        "content": k.content,
        "category": k.category,
        "source_type": k.source_type,
        "source_id": k.source_id,
        "tags": k.tag_list,
        "confidence_score": k.confidence_score,
        "review_status": k.review_status,
        "last_validated_at": k.last_validated_at.isoformat() if k.last_validated_at else None,
        "created_by": k.created_by,
        "created_at": k.created_at.isoformat() if k.created_at else None,
        "updated_at": k.updated_at.isoformat() if k.updated_at else None,
    }


class KnowledgeService:
    def __init__(self, db: Session):
        self.db = db

    # ---------- CRUD ----------

    def list_items(self, category: Optional[str] = None, review_status: Optional[str] = None,
                   q: Optional[str] = None, skip: int = 0, limit: int = 20) -> dict:
        self.mark_stale()  # 懒触发老化（幂等 UPDATE）
        query = self.db.query(Knowledge)
        if category:
            query = query.filter(Knowledge.category == category)
        if review_status:
            query = query.filter(Knowledge.review_status == review_status)
        if q:
            like = f"%{q}%"
            query = query.filter(or_(
                Knowledge.title.ilike(like),
                Knowledge.content.ilike(like),
                Knowledge.tags.ilike(like),
            ))
        total = query.count()
        items = query.order_by(Knowledge.updated_at.desc()).offset(skip).limit(limit).all()
        return {"total": total, "items": [_to_out(k) for k in items]}

    def create(self, data: dict, created_by: Optional[str] = None) -> Knowledge:
        k = Knowledge(
            title=data["title"],
            content=data["content"],
            category=data.get("category") or "troubleshooting",
            source_type=data.get("source_type") or "manual",
            source_id=data.get("source_id"),
            tags=", ".join(data.get("tags") or []),
            confidence_score=90 if (data.get("source_type") or "manual") == "manual" else 70,
            last_validated_at=_utcnow() if (data.get("source_type") or "manual") == "manual" else None,
            created_by=created_by,
        )
        self.db.add(k)
        self.db.commit()
        self.db.refresh(k)
        return k

    def update(self, knowledge_id, data: dict) -> Optional[Knowledge]:
        k = self.db.query(Knowledge).filter(Knowledge.id == knowledge_id).first()
        if not k:
            return None
        for field in ("title", "content", "category", "tags"):
            if field in data and data[field] is not None:
                setattr(k, field, ", ".join(data[field]) if field == "tags" and isinstance(data[field], list) else data[field])
        self.db.commit()
        self.db.refresh(k)
        return k

    def delete(self, knowledge_id) -> bool:
        k = self.db.query(Knowledge).filter(Knowledge.id == knowledge_id).first()
        if not k:
            return False
        self.db.delete(k)
        self.db.commit()
        return True

    def validate(self, knowledge_id) -> Optional[Knowledge]:
        """人工验证：刷新时间 + confidence 90 + 回到 active（PRD 老化管理）"""
        k = self.db.query(Knowledge).filter(Knowledge.id == knowledge_id).first()
        if not k:
            return None
        k.last_validated_at = _utcnow()
        k.confidence_score = 90
        k.review_status = "active"
        self.db.commit()
        self.db.refresh(k)
        return k

    def mark_stale(self) -> int:
        """老化基准 = COALESCE(last_validated_at, created_at)：未验证的新提取知识
        不会误入待复审；幂等 UPDATE。"""
        cutoff = _utcnow() - timedelta(days=STALE_MONTHS * 30)
        return (
            self.db.query(Knowledge)
            .filter(
                Knowledge.review_status == "active",
                Knowledge.id.in_(
                    self.db.query(Knowledge.id).filter(
                        func.coalesce(Knowledge.last_validated_at, Knowledge.created_at) < cutoff
                    )
                ),
            )
            .update({"review_status": "pending_review"}, synchronize_session=False)
        )

    # ---------- 自动提取（事件 → 知识三元组） ----------

    @staticmethod
    def _fallback_extract(inc: Incident) -> dict:
        """GLM 不可用时的模板整理（§八-C：降级而非失败）。"""
        notes = (inc.resolution_notes or "").strip()
        return {
            "title": f"{inc.title[:80]}",
            "content": (
                f"【故障】{inc.title}\n"
                f"【现象/描述】{(inc.description or '').strip()[:400] or '（事件描述缺失）'}\n"
                f"【原因】（待补充：AI 提取暂不可用，请人工完善）\n"
                f"【解决方案】{notes[:600] if notes else '（处理备注缺失，请人工补充）'}\n"
                f"【关联】事件 {inc.id}（{inc.severity}，{inc.status}）"
            ),
            "category": "troubleshooting",
            "tags": [inc.severity, "事件复盘"],
        }

    def _glm_extract(self, inc: Incident) -> Optional[dict]:
        if not ai_budget.allow():
            return None
        try:
            from zhipuai import ZhipuAI
            from app.core.config import settings
            client = ZhipuAI(api_key=settings.GLM_API_KEY)
            ai_part = ""
            if inc.ai_analysis:
                ai_part = (
                    f"\nAI研判（参考）：{inc.ai_analysis.risk_assessment or ''}"
                    f"\n处置建议（参考）：{inc.ai_analysis.recommendations or ''}"
                )
            prompt = (
                "你是运维知识管理专家。从已解决的安全事件中提取一条可复用的运维知识，"
                "输出 JSON（不要其他文字）：\n"
                '{"title": "简短标题(30字内)", "symptom": "故障现象", '
                '"cause": "根本原因(依据事件信息,不确定写待确认)", '
                '"solution": "解决方案/处置步骤", "category": "troubleshooting|configuration|policy|reference", '
                '"tags": ["标签1","标签2"]}\n\n'
                f"事件标题: {inc.title}\n"
                f"严重度: {inc.severity}\n"
                f"事件描述: {(inc.description or '')[:600]}\n"
                f"处理备注: {(inc.resolution_notes or '')[:600]}"
                f"{ai_part}"
            )
            resp = client.chat.completions.create(
                model=settings.GLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
            )
            ai_budget.record_success()
            m = re.search(r"\{.*\}", resp.choices[0].message.content or "", re.S)
            if not m:
                return None
            d = json.loads(m.group(0))
            category = str(d.get("category", "troubleshooting"))
            content = (
                f"【故障】{d.get('symptom', inc.title)}\n"
                f"【原因】{d.get('cause', '待确认')}\n"
                f"【解决方案】{d.get('solution', (inc.resolution_notes or '待补充'))}\n"
                f"【关联】事件 {inc.id}（{inc.severity}）"
            )
            return {
                "title": str(d.get("title") or inc.title)[:120],
                "content": content,
                "category": category if category in VALID_CATEGORIES else "troubleshooting",
                "tags": [str(t)[:30] for t in (d.get("tags") or [])][:6],
            }
        except Exception as e:
            ai_budget.record_failure()
            logger.warning("知识提取 GLM 失败，走模板降级: %s", e)
            return None

    def auto_extract(self, days: int = 90, force: bool = False) -> dict:
        """从已解决/关闭事件批量提取。返回统计（extracted/skipped/errors + source）。"""
        since = _utcnow() - timedelta(days=min(max(days, 1), 365))
        query = self.db.query(Incident).filter(
            Incident.status.in_(("resolved", "closed")),
            Incident.updated_at >= since,
        )
        if not force:
            done = {
                row[0]
                for row in self.db.query(Knowledge.source_id)
                .filter(Knowledge.source_type == "incident_summary")
                .all()
            }
        else:
            done = set()
        incidents = [i for i in query.order_by(Incident.updated_at.desc()).all()
                     if str(i.id) not in done][:EXTRACT_BATCH_LIMIT]

        stats = {"candidates": len(incidents), "extracted": 0, "source": {"glm": 0, "rule": 0}, "errors": 0}
        for inc in incidents:
            try:
                extracted = self._glm_extract(inc)
                source = "glm"
                if extracted is None:
                    extracted = self._fallback_extract(inc)
                    source = "rule"
                self.db.add(Knowledge(
                    title=extracted["title"],
                    content=extracted["content"],
                    category=extracted["category"],
                    source_type="incident_summary",
                    source_id=str(inc.id),
                    tags=", ".join(extracted["tags"]),
                    confidence_score=70,
                    created_by=f"auto:{source}",
                ))
                stats["extracted"] += 1
                stats["source"][source] += 1
            except Exception as e:
                stats["errors"] += 1
                logger.error("事件 %s 知识提取失败: %s", inc.id, e)
        self.db.commit()
        logger.info("知识自动提取完成: %s", stats)
        return stats

    # ---------- 智能检索（召回 + rerank） ----------

    def _recall(self, question: str) -> list:
        """关键词召回：分词朴素切分（中文按 2-gram + 原词），ilike 匹配。"""
        tokens = {question.strip()} | {
            question[i:i + 2] for i in range(len(question) - 1)
        } if len(question) >= 2 else {question}
        tokens = {t for t in tokens if len(t) >= 2}
        if not tokens:
            return []
        conditions = []
        for t in list(tokens)[:12]:
            like = f"%{t}%"
            conditions.extend([
                Knowledge.title.ilike(like),
                Knowledge.content.ilike(like),
                Knowledge.tags.ilike(like),
            ])
        rows = (
            self.db.query(Knowledge)
            .filter(or_(*conditions))
            .order_by(Knowledge.confidence_score.desc(), Knowledge.updated_at.desc())
            .limit(SEARCH_RECALL_LIMIT)
            .all()
        )
        # 召回得分：命中 token 数（title 命中加权）
        def score(k: Knowledge) -> int:
            s = 0
            hay_t, hay_c = (k.title or "").lower(), (k.content or "").lower()
            for t in tokens:
                if t.lower() in hay_t:
                    s += 3
                elif t.lower() in hay_c:
                    s += 1
            if k.review_status == "pending_review":
                s -= 2  # 老化知识降权（PRD：待复审标黄 + 降权）
            return s
        rows.sort(key=score, reverse=True)
        return rows

    def _rerank(self, question: str, candidates: list) -> Optional[list]:
        """GLM rerank：返回按相关性排序的 id 列表；不可用返回 None。"""
        if not ai_budget.allow():
            return None
        try:
            from zhipuai import ZhipuAI
            from app.core.config import settings
            client = ZhipuAI(api_key=settings.GLM_API_KEY)
            docs = [{"id": str(k.id), "title": k.title,
                     "excerpt": (k.content or "")[:200]} for k in candidates]
            prompt = (
                "你是检索助手。根据用户问题对知识条目按相关性排序（最相关的在前）。"
                "只输出 JSON 数组（按相关性降序的 id 列表），不要其他文字。\n"
                f"用户问题: {question}\n候选知识: {json.dumps(docs, ensure_ascii=False)}"
            )
            resp = client.chat.completions.create(
                model=settings.GLM_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
            ai_budget.record_success()
            m = re.search(r"\[.*\]", resp.choices[0].message.content or "", re.S)
            if not m:
                return None
            order = json.loads(m.group(0))
            by_id = {str(k.id): k for k in candidates}
            ranked = [by_id[i] for i in order if i in by_id]
            # GLM 遗漏的候选追加在后（不丢结果）
            missing = [k for k in candidates if k not in ranked]
            return ranked + missing
        except Exception as e:
            ai_budget.record_failure()
            logger.warning("知识 rerank GLM 失败，用召回顺序: %s", e)
            return None

    def search(self, question: str) -> dict:
        question = (question or "").strip()
        if not question:
            return {"question": "", "results": [], "rerank_source": None, "message": "请输入问题"}
        candidates = self._recall(question)
        if not candidates:
            # 诚实返回空（§八-C：不编造）；给引导
            return {
                "question": question, "results": [], "rerank_source": None,
                "message": "知识库中未找到相关知识。可先「AI 提取」从已解决事件生成知识，或手动录入。",
            }
        ranked = self._rerank(question, candidates)
        rerank_source = "glm"
        if ranked is None:
            ranked = candidates
            rerank_source = "recall"
        return {
            "question": question,
            "results": [_to_out(k) for k in ranked[:8]],
            "rerank_source": rerank_source,
        }
