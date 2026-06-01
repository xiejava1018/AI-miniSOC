"""
字典管理 API
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_admin
from app.core.audit_decorator import log_audit
from app.schemas.user import UserResponse as UserResponseSchema
from app.schemas.dict import (
    DictCreate,
    DictUpdate,
    DictResponse,
    DictListResponse,
)
from app.services.dict_service import DictService


router = APIRouter()


@router.get("/types", response_model=List[str])
async def get_dict_types(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取所有字典分类列表"""
    service = DictService(db)
    return service.get_all_types()


@router.get("", response_model=DictListResponse)
async def get_dict_list(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    dict_type: Optional[str] = Query(None, description="字典类型"),
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取字典列表（分页）"""
    service = DictService(db)
    skip = (page - 1) * page_size
    items, total = service.get_list(skip=skip, limit=page_size, search=search, dict_type=dict_type)
    return DictListResponse(
        total=total,
        items=[DictResponse.model_validate(i) for i in items],
        page=page,
        page_size=page_size,
    )


@router.get("/{dict_type}/items", response_model=List[DictResponse])
async def get_dicts_by_type(
    dict_type: str,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按类型获取全部字典项（不分页，前端缓存用）"""
    service = DictService(db)
    items = service.get_by_type(dict_type)
    return [DictResponse.model_validate(i) for i in items]


@router.post("", response_model=DictResponse, status_code=status.HTTP_201_CREATED)
@log_audit(
    action="CREATE",
    resource_type="dict",
    get_resource_id=lambda result, kwargs: result.id if hasattr(result, 'id') else None,
    get_resource_name=lambda result, kwargs: f"{result.dict_type}:{result.dict_code}" if hasattr(result, 'dict_type') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None,
)
async def create_dict(
    request: Request,
    data: DictCreate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """新增字典项（仅管理员）"""
    service = DictService(db)
    try:
        item = service.create(data)
        return DictResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.put("/{dict_id}", response_model=DictResponse)
@log_audit(
    action="UPDATE",
    resource_type="dict",
    get_resource_id=lambda result, kwargs: kwargs.get('dict_id'),
    get_resource_name=lambda result, kwargs: f"{result.dict_type}:{result.dict_code}" if hasattr(result, 'dict_type') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None,
)
async def update_dict(
    request: Request,
    dict_id: int,
    data: DictUpdate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """更新字典项（仅管理员）"""
    service = DictService(db)
    try:
        item = service.update(dict_id, data)
        return DictResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{dict_id}")
@log_audit(
    action="DELETE",
    resource_type="dict",
    get_resource_id=lambda result, kwargs: kwargs.get('dict_id'),
)
async def delete_dict(
    request: Request,
    dict_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """删除字典项（仅管理员）"""
    service = DictService(db)
    try:
        service.delete(dict_id)
        return {"success": True, "message": "字典项已删除"}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
