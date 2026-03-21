# src/backend/app/api/menus.py
from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.schemas.user import UserResponse as UserResponseSchema
from app.schemas.menu import MenuTreeResponse
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
