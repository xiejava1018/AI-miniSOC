"""
自然语言资产查询 API（PRD F2.1 L1，P3 MVP）

挂在 /assets 前缀；必须在 assets.router 之前注册
（GET /ask 单段静态路径，否则被 assets 的 GET /{asset_id} 抢匹配，Starlette 按注册顺序）。
"""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import User
from app.services.asset_query import AssetQueryService

logger = logging.getLogger(__name__)
router = APIRouter()


class AskRequest(BaseModel):
    question: str
    session_id: str | None = None  # 传入则续接会话（多轮），否则新建


@router.post("/ask")
def ask_asset_query(
    body: AskRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """L1 自然语言查询：意图识别 → 资产筛选/统计 → AI 摘要（参数 chips 由前端回显）"""
    svc = AssetQueryService(db)
    return svc.ask(body.question, user_id=current_user.id, session_id=body.session_id)


@router.get("/ask/history")
def ask_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """当前用户的查询历史（支持一键重放）"""
    svc = AssetQueryService(db)
    return {"history": svc.history(user_id=current_user.id, limit=min(max(limit, 1), 100))}
