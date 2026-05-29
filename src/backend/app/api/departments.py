# src/backend/app/api/departments.py
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_admin
from app.core.audit_decorator import log_audit
from app.schemas.user import UserResponse as UserResponseSchema
from app.schemas.department import (
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentResponse,
    DepartmentListResponse,
    DepartmentTreeNode
)
from app.services.department_service import DepartmentService


router = APIRouter(tags=["部门管理"])


@router.get("/tree", response_model=List[DepartmentTreeNode])
async def get_department_tree(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取部门树形结构"""
    service = DepartmentService(db)
    tree = service.get_department_tree()
    return [DepartmentTreeNode.model_validate(node) for node in tree]


@router.get("", response_model=DepartmentListResponse)
async def get_departments(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量"),
    name: Optional[str] = Query(None, description="部门名称"),
    status: Optional[int] = Query(None, ge=1, le=2, description="状态: 1=启用, 2=禁用"),
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取部门列表"""
    service = DepartmentService(db)
    skip = (page - 1) * page_size

    departments, total = service.get_departments(
        skip=skip,
        limit=page_size,
        name=name,
        status=status
    )

    items = [DepartmentResponse.model_validate(d) for d in departments]

    return DepartmentListResponse(
        total=total,
        items=items,
        page=page,
        page_size=page_size
    )


@router.post("", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
@log_audit(
    action="CREATE",
    resource_type="department",
    get_resource_id=lambda result, kwargs: result.id if hasattr(result, 'id') else None,
    get_resource_name=lambda result, kwargs: result.name if hasattr(result, 'name') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None
)
async def create_department(
    request: Request,
    data: DepartmentCreate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """创建部门（仅管理员）"""
    service = DepartmentService(db)
    try:
        department = service.create_department(data)
        return DepartmentResponse.model_validate(department)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{department_id}", response_model=DepartmentResponse)
async def get_department(
    department_id: int,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取部门详情"""
    service = DepartmentService(db)
    try:
        department = service.get_department_by_id(department_id)
        return DepartmentResponse.model_validate(department)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.put("/{department_id}", response_model=DepartmentResponse)
@log_audit(
    action="UPDATE",
    resource_type="department",
    get_resource_id=lambda result, kwargs: kwargs.get('department_id'),
    get_resource_name=lambda result, kwargs: result.name if hasattr(result, 'name') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None
)
async def update_department(
    request: Request,
    department_id: int,
    data: DepartmentUpdate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """更新部门（仅管理员）"""
    service = DepartmentService(db)
    try:
        department = service.update_department(department_id, data)
        return DepartmentResponse.model_validate(department)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{department_id}")
@log_audit(
    action="DELETE",
    resource_type="department",
    get_resource_id=lambda result, kwargs: kwargs.get('department_id')
)
async def delete_department(
    request: Request,
    department_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """删除部门（仅管理员）"""
    service = DepartmentService(db)
    try:
        service.delete_department(department_id)
        return {"success": True, "message": "部门已删除"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
