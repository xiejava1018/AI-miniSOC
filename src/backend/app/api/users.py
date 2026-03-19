# api/users.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_menu_permission
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


router = APIRouter(prefix="/users", tags=["用户管理"])


@router.get("", response_model=UserListResponse)
async def get_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    role_id: Optional[int] = Query(None, description="角色ID"),
    status: Optional[str] = Query(None, description="状态"),
    current_user: UserResponseSchema = Depends(require_menu_permission("system-users")),
    db: Session = Depends(get_db)
):
    """
    获取用户列表

    需要权限: system-users
    """
    service = UserService(db)
    skip = (page - 1) * page_size

    users, total = service.get_users(
        skip=skip,
        limit=page_size,
        search=search,
        role_id=role_id,
        status=status
    )

    return UserListResponse(
        total=total,
        items=[UserResponse.model_validate(u) for u in users]
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: UserResponseSchema = Depends(require_menu_permission("system-users")),
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

    return UserResponse.model_validate(user)


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
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
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
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
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{user_id}")
async def delete_user(
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
async def reset_password(
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
async def lock_user(
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
        return UserResponse.model_validate(user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
