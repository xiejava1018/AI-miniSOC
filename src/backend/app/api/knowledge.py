"""
运维知识库 API（PRD F2.3，P3 W8）

- POST /knowledge/search        自然语言搜索（召回+GLM rerank）
- GET  /knowledge               列表（category/review_status/关键词过滤 + 懒老化）
- POST /knowledge               手动创建（operator+，confidence=90）
- PUT  /knowledge/{id}          编辑（operator+）
- DELETE /knowledge/{id}        删除（admin）
- POST /knowledge/{id}/validate 人工验证（刷新时间 + confidence 90）
- POST /knowledge/auto-extract  从已解决事件批量提取（admin）
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import User
from app.services.knowledge_service import KnowledgeService

logger = logging.getLogger(__name__)
router = APIRouter()


def _require_admin(current_user: User) -> None:
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")


class SearchRequest(BaseModel):
    question: str


class KnowledgeCreate(BaseModel):
    title: str
    content: str
    category: Optional[str] = "troubleshooting"
    tags: Optional[list[str]] = None

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("标题不能为空")
        return v.strip()


class KnowledgeUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[list[str]] = None


@router.post("/search")
def search_knowledge(
    body: SearchRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """自然语言搜索：关键词召回 + GLM rerank（预算限流，降级为召回顺序）"""
    return KnowledgeService(db).search(body.question)


@router.get("")
def list_knowledge(
    category: Optional[str] = None,
    review_status: Optional[str] = None,
    q: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    return KnowledgeService(db).list_items(category, review_status, q, skip, limit)


@router.post("")
def create_knowledge(
    body: KnowledgeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    k = KnowledgeService(db).create(body.model_dump(), created_by=current_user.username)
    return {"id": str(k.id), "message": "知识条目已创建"}


@router.put("/{knowledge_id}")
def update_knowledge(
    knowledge_id: str,
    body: KnowledgeUpdate,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    from uuid import UUID
    try:
        kid = UUID(knowledge_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID 格式错误")
    k = KnowledgeService(db).update(kid, body.model_dump(exclude_none=True))
    if not k:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return {"message": "已更新"}


@router.delete("/{knowledge_id}")
def delete_knowledge(
    knowledge_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    from uuid import UUID
    try:
        kid = UUID(knowledge_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID 格式错误")
    if not KnowledgeService(db).delete(kid):
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return {"message": "已删除"}


@router.post("/{knowledge_id}/validate")
def validate_knowledge(
    knowledge_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """人工验证：刷新 last_validated_at + confidence 90 + 回 active"""
    from uuid import UUID
    try:
        kid = UUID(knowledge_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="ID 格式错误")
    k = KnowledgeService(db).validate(kid)
    if not k:
        raise HTTPException(status_code=404, detail="知识条目不存在")
    return {"message": "已验证", "confidence_score": k.confidence_score}


@router.post("/auto-extract")
def auto_extract(
    days: int = Query(90, ge=1, le=365),
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从已解决/关闭事件批量提取知识三元组（admin；GLM 失败降级模板整理）"""
    _require_admin(current_user)
    stats = KnowledgeService(db).auto_extract(days=days, force=force)
    return {"message": "提取完成", "stats": stats}
