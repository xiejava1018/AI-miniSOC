# api/users.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_menu_permission
from app.core.audit_decorator import log_audit
from app.schemas.user import (
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    ResetPasswordRequest,
    LockUserRequest
)
from app.services.user_service import UserService
from app.schemas.user import UserResponse as UserResponseSchema
from app.models.user import UserStatus


router = APIRouter(tags=["用户管理"])


def _build_user_response(user) -> UserResponse:
    """构建用户响应，处理关联数据"""
    data = {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "full_name": user.full_name,
        "nick_name": user.nick_name,
        "phone": user.phone,
        "avatar": user.avatar,
        "gender": user.gender,
        "department_id": user.department_id,
        "department_name": user.department.name if user.department else None,
        "role_id": user.role_id,
        "role_name": user.role.name if user.role else None,
        "is_admin": user.is_admin,
        "status": user.status,
        "last_login": user.last_login,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }
    return UserResponse.model_validate(data)


@router.get("", response_model=UserListResponse)
async def get_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    role_id: Optional[int] = Query(None, description="角色ID"),
    status: Optional[int] = Query(None, ge=1, le=2, description="状态: 1=启用, 2=禁用"),
    current_user: UserResponseSchema = Depends(require_menu_permission("users")),
    db: Session = Depends(get_db)
):
    """
    获取用户列表

    需要权限: system-users
    """
    service = UserService(db)
    skip = (page - 1) * page_size

    # 状态转换：前端数字 -> 后端字符串
    status_str = None
    if status is not None:
        status_map = {1: UserStatus.ACTIVE, 2: UserStatus.DISABLED}
        status_str = status_map.get(status, UserStatus.ACTIVE)

    users, total = service.get_users(
        skip=skip,
        limit=page_size,
        search=search,
        role_id=role_id,
        status=status_str
    )

    return UserListResponse(
        total=total,
        items=[_build_user_response(u) for u in users]
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: UserResponseSchema = Depends(require_menu_permission("users")),
    db: Session = Depends(get_db)
):
    """获取用户详情"""
    service = UserService(db)
    user = service.get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="用户不存在"
        )

    return _build_user_response(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@log_audit(
    action="CREATE",
    resource_type="user",
    get_resource_id=lambda result, kwargs: result.id if hasattr(result, 'id') else None,
    get_resource_name=lambda result, kwargs: result.username if hasattr(result, 'username') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None
)
async def create_user(
    request: Request,
    user_data: UserCreate,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    创建用户

    需要权限: 仅管理员
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以创建用户"
        )

    service = UserService(db)
    try:
        user = service.create_user(user_data, creator_id=current_user.id)
        return _build_user_response(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{user_id}", response_model=UserResponse)
@log_audit(
    action="UPDATE",
    resource_type="user",
    get_resource_id=lambda result, kwargs: kwargs.get('user_id'),
    get_resource_name=lambda result, kwargs: result.username if hasattr(result, 'username') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None
)
async def update_user(
    request: Request,
    user_id: int,
    user_data: UserUpdate,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    更新用户

    需要权限: 仅管理员
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以更新用户"
        )

    service = UserService(db)
    try:
        user = service.update_user(user_id, user_data, updater_id=current_user.id)
        return _build_user_response(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{user_id}")
@log_audit(
    action="DELETE",
    resource_type="user",
    get_resource_id=lambda result, kwargs: kwargs.get('user_id')
)
async def delete_user(
    request: Request,
    user_id: int,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    删除用户

    需要权限: 仅管理员
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以删除用户"
        )

    service = UserService(db)
    try:
        service.delete_user(user_id, deleter_id=current_user.id)
        return {"success": True, "message": "用户已删除"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{user_id}/reset-password")
@log_audit(
    action="RESET_PASSWORD",
    resource_type="user",
    get_resource_id=lambda result, kwargs: kwargs.get('user_id')
)
async def reset_password(
    request: Request,
    user_id: int,
    password_data: ResetPasswordRequest,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    重置用户密码

    需要权限: 仅管理员
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以重置密码"
        )

    service = UserService(db)
    try:
        new_password = service.reset_password(
            user_id,
            new_password=password_data.new_password,
            admin_id=current_user.id
        )
        return {
            "success": True,
            "message": "密码已重置",
            "new_password": new_password
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{user_id}/lock", response_model=UserResponse)
@log_audit(
    action="LOCK",
    resource_type="user",
    get_resource_id=lambda result, kwargs: kwargs.get('user_id'),
    get_resource_name=lambda result, kwargs: result.username if hasattr(result, 'username') else None,
    get_new_values=lambda result, kwargs: {"is_locked": kwargs.get('lock_data').is_locked, "lock_reason": kwargs.get('lock_data').lock_reason}
)
async def lock_user(
    request: Request,
    user_id: int,
    lock_data: LockUserRequest,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    锁定或解锁用户

    需要权限: 仅管理员
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有管理员可以锁定用户"
        )

    service = UserService(db)
    try:
        user = service.lock_user(
            user_id,
            locked=lock_data.is_locked,
            reason=lock_data.lock_reason,
            admin_id=current_user.id
        )
        return _build_user_response(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
