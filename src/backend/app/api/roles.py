# src/backend/app/api/roles.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_admin
from app.schemas.user import UserResponse as UserResponseSchema
from app.schemas.role import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleListResponse,
    RoleMenusRequest
)
from app.services.role_service import RoleService


router = APIRouter(prefix="/roles", tags=["角色管理"])


@router.get("", response_model=RoleListResponse)
async def get_roles(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    search: Optional[str] = Query(None, description="搜索关键词"),
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """
    获取角色列表

    需要权限: admin
    """
    service = RoleService(db)
    skip = (page - 1) * page_size

    roles, total = service.get_roles(
        skip=skip,
        limit=page_size,
        search=search
    )

    # 为每个角色添加用户数
    items = []
    for role in roles:
        role_dict = RoleResponse.model_validate(role).model_dump()
        role_dict['user_count'] = len(service.get_role_users(role.id))
        items.append(RoleResponse(**role_dict))

    return RoleListResponse(
        total=total,
        items=items,
        page=page,
        page_size=page_size
    )


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """获取角色详情"""
    service = RoleService(db)
    try:
        role = service.get_role_by_id(role_id)
        role_dict = RoleResponse.model_validate(role).model_dump()
        role_dict['user_count'] = len(service.get_role_users(role_id))
        return RoleResponse(**role_dict)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    role_data: RoleCreate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """
    创建角色

    需要权限: admin
    """
    service = RoleService(db)
    try:
        role = service.create_role(role_data, creator_id=current_user.id)
        role_dict = RoleResponse.model_validate(role).model_dump()
        role_dict['user_count'] = 0
        return RoleResponse(**role_dict)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    role_data: RoleUpdate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """
    更新角色

    需要权限: admin
    """
    service = RoleService(db)
    try:
        role = service.update_role(role_id, role_data, updater_id=current_user.id)
        role_dict = RoleResponse.model_validate(role).model_dump()
        role_dict['user_count'] = len(service.get_role_users(role_id))
        return RoleResponse(**role_dict)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{role_id}")
async def delete_role(
    role_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """
    删除角色

    需要权限: admin
    """
    service = RoleService(db)
    try:
        service.delete_role(role_id, deleter_id=current_user.id)
        return {"success": True, "message": "角色已删除"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{role_id}/menus")
async def get_role_menus(
    role_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """获取角色的菜单列表"""
    service = RoleService(db)
    try:
        menus = service.get_role_menus(role_id)
        return {
            "role_id": role_id,
            "menu_ids": [menu.id for menu in menus],
            "menus": [menu.to_dict() for menu in menus]
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.put("/{role_id}/menus")
async def assign_role_menus(
    role_id: int,
    menus_data: RoleMenusRequest,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """分配菜单权限"""
    service = RoleService(db)
    try:
        role = service.assign_menus(role_id, menus_data.menu_ids)
        return {
            "success": True,
            "message": "菜单权限已分配",
            "role": RoleResponse.model_validate(role).model_dump()
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{role_id}/users")
async def get_role_users(
    role_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """获取使用该角色的用户列表"""
    service = RoleService(db)
    try:
        users = service.get_role_users(role_id)
        return {
            "role_id": role_id,
            "users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                    "email": user.email,
                    "status": user.status
                }
                for user in users
            ]
        }
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
