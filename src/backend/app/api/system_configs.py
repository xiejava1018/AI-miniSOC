"""系统配置 API"""
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_admin
from app.core.audit_decorator import log_audit
from app.schemas.user import UserResponse as UserResponseSchema
from app.schemas.system_config import (
    SystemConfigCreate,
    SystemConfigUpdate,
    SystemConfigResponse,
    SystemConfigListResponse,
    CategoryItem,
)
from app.services.system_config_service import SystemConfigService


router = APIRouter()


@router.get("/categories", response_model=List[CategoryItem])
async def get_config_categories(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取所有配置分类及数量"""
    service = SystemConfigService(db)
    return service.get_all_categories()


@router.get("/by-category/{category}", response_model=List[SystemConfigResponse])
async def get_configs_by_category(
    category: str,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """按分类取全部配置（不分页）"""
    service = SystemConfigService(db)
    items = service.get_by_category(category)
    return [SystemConfigResponse.model_validate(i) for i in items]


@router.get("", response_model=SystemConfigListResponse)
async def get_config_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """分页获取配置列表"""
    service = SystemConfigService(db)
    skip = (page - 1) * page_size
    items, total = service.get_list(
        skip=skip, limit=page_size, search=search, category=category
    )
    return SystemConfigListResponse(
        total=total,
        items=[SystemConfigResponse.model_validate(i) for i in items],
        page=page,
        page_size=page_size,
    )


@router.get("/{config_id}", response_model=SystemConfigResponse)
async def get_config(
    config_id: int,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    service = SystemConfigService(db)
    try:
        item = service.get_by_id(config_id)
        return SystemConfigResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("", response_model=SystemConfigResponse, status_code=status.HTTP_201_CREATED)
@log_audit(
    action="CREATE",
    resource_type="system_config",
    get_resource_id=lambda result, kwargs: result.id if hasattr(result, 'id') else None,
    get_resource_name=lambda result, kwargs: f"{result.category}.{result.key}" if hasattr(result, 'category') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None,
)
async def create_config(
    request: Request,
    data: SystemConfigCreate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    service = SystemConfigService(db)
    try:
        item = service.create(data, user_id=current_user.id)
        return SystemConfigResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{config_id}", response_model=SystemConfigResponse)
@log_audit(
    action="UPDATE",
    resource_type="system_config",
    get_resource_id=lambda result, kwargs: kwargs.get('config_id'),
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None,
)
async def update_config(
    request: Request,
    config_id: int,
    data: SystemConfigUpdate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    service = SystemConfigService(db)
    try:
        item = service.update(config_id, data, user_id=current_user.id)
        return SystemConfigResponse.model_validate(item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{config_id}")
@log_audit(
    action="DELETE",
    resource_type="system_config",
    get_resource_id=lambda result, kwargs: kwargs.get('config_id'),
)
async def delete_config(
    request: Request,
    config_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    service = SystemConfigService(db)
    try:
        service.delete(config_id)
        return {"success": True, "message": "配置项已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
