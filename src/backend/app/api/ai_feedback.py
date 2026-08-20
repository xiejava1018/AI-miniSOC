"""
AI 反馈 API（PRD F4.1 反馈闭环，P3 MVP）

所有 AI 产物（risk_summary / security_summary / query / report / knowledge）
统一 👍/👎 + 可选修正文本。月度汇总接口供运营侧观察 👎 率（>20% 触发 Prompt 迭代评审）。
挂在 /ai 前缀（与 ai_agent 同模式，多个 router 共享前缀）。
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import User
from app.models.ai_feedback import AiFeedback

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_TARGET_TYPES = {"risk_summary", "security_summary", "query", "report", "knowledge"}


class FeedbackCreate(BaseModel):
    target_type: str
    target_id: str
    rating: str  # up / down
    comment: str | None = None

    @field_validator("rating")
    @classmethod
    def _rating(cls, v: str) -> str:
        v = (v or "").lower()
        if v not in ("up", "down"):
            raise ValueError("rating 只能为 up / down")
        return v


@router.post("/feedback")
def submit_feedback(
    body: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """提交 AI 产物反馈（幂等友好：同一产物可多次反馈，取最新）"""
    if body.target_type not in VALID_TARGET_TYPES:
        raise HTTPException(status_code=400, detail=f"target_type 须为 {sorted(VALID_TARGET_TYPES)} 之一")
    if not body.target_id:
        raise HTTPException(status_code=400, detail="target_id 不能为空")
    fb = AiFeedback(
        target_type=body.target_type,
        target_id=body.target_id,
        rating=body.rating,
        comment=(body.comment or "").strip() or None,
        user_id=current_user.id,
    )
    db.add(fb)
    db.commit()
    return {"message": "反馈已记录，感谢", "id": str(fb.id)}


@router.get("/feedback/summary")
def feedback_summary(
    days: int = 30,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """反馈汇总（admin）：按 target_type 分列 up/down/👍率，👎 率 >20% 标记需评审"""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    since = datetime.now(timezone.utc) - timedelta(days=min(max(days, 1), 365))
    rows = (
        db.query(
            AiFeedback.target_type,
            AiFeedback.rating,
            func.count(AiFeedback.id),
        )
        .filter(AiFeedback.created_at >= since)
        .group_by(AiFeedback.target_type, AiFeedback.rating)
        .all()
    )
    agg: dict = {}
    for target_type, rating, cnt in rows:
        slot = agg.setdefault(target_type, {"up": 0, "down": 0})
        slot[rating] = cnt
    summary = []
    for target_type, slot in sorted(agg.items()):
        total = slot["up"] + slot["down"]
        up_rate = round(slot["up"] / total * 100, 1) if total else None
        summary.append({
            "target_type": target_type,
            "up": slot["up"],
            "down": slot["down"],
            "total": total,
            "up_rate_percent": up_rate,
            "needs_prompt_review": total > 0 and (slot["down"] / total) > 0.2,
        })
    return {"days": days, "summary": summary}
