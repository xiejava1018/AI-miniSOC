# src/backend/app/api/menus.py
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_admin
from app.schemas.user import UserResponse as UserResponseSchema
from app.schemas.menu import (
    MenuCreate,
    MenuUpdate,
    MenuResponse,
    MenuTreeResponse
)
from app.services.menu_service import MenuService


router = APIRouter(prefix="/menus", tags=["菜单管理"])


@router.get("/tree", response_model=List[MenuTreeResponse])
async def get_menu_tree(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取菜单树（所有用户可访问）"""
    service = MenuService(db)
    menus = service.get_menu_tree()
    return [MenuTreeResponse.model_validate(m) for m in menus]


@router.get("/options")
async def get_menu_options(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取菜单选项（用于父菜单选择）"""
    service = MenuService(db)
    return service.get_menu_options()


@router.get("", response_model=list[MenuResponse])
async def get_menus(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取所有菜单（平铺列表）"""
    service = MenuService(db)
    menus = service.get_all_menus()
    return [MenuResponse.model_validate(m) for m in menus]


@router.post("", response_model=MenuResponse, status_code=status.HTTP_201_CREATED)
async def create_menu(
    menu_data: MenuCreate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """创建菜单（仅管理员）"""
    service = MenuService(db)
    try:
        menu = service.create_menu(menu_data)
        return MenuResponse.model_validate(menu)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/{menu_id}", response_model=MenuResponse)
async def get_menu(
    menu_id: int,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取菜单详情"""
    service = MenuService(db)
    try:
        menu = service.get_menu_by_id(menu_id)
        return MenuResponse.model_validate(menu)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.put("/{menu_id}", response_model=MenuResponse)
async def update_menu(
    menu_id: int,
    menu_data: MenuUpdate,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """更新菜单（仅管理员）"""
    service = MenuService(db)
    try:
        menu = service.update_menu(menu_id, menu_data)
        return MenuResponse.model_validate(menu)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.delete("/{menu_id}")
async def delete_menu(
    menu_id: int,
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db)
):
    """删除菜单（仅管理员）"""
    service = MenuService(db)
    try:
        service.delete_menu(menu_id)
        return {"success": True, "message": "菜单已删除"}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
