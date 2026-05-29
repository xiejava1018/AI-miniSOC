# src/backend/app/api/menus.py
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.auth import get_current_user
from app.core.permissions import require_admin
from app.core.audit_decorator import log_audit
from app.schemas.user import UserResponse as UserResponseSchema
from app.schemas.menu import (
    MenuCreate,
    MenuUpdate,
    MenuResponse,
    MenuTreeResponse
)
from app.services.menu_service import MenuService


router = APIRouter(tags=["菜单管理"])


def _build_menu_with_auth(menu, role_perms: dict) -> dict:
    """构建带权限信息的菜单字典（包含 meta 字段，与前端表格列对齐）"""
    data = menu.to_dict(include_children=True)
    available = data.get('permissions') or []
    granted = role_perms.get(menu.id, [])
    auth_list = [
        {**p, 'hasPermission': p.get('authMark') in granted}
        for p in available
    ] if available else []
    data['authList'] = auth_list
    data['hasPermission'] = True
    # 构建 meta 字段（与前端 columns prop 对齐）
    data['meta'] = {
        'title': data.get('title') or data.get('name') or '',
        'icon': data.get('icon') or '',
        'isEnable': data.get('is_visible', True),
        'keepAlive': True,
        'authList': auth_list,
        'isHide': False,
        'isHideTab': False,
        'isIframe': False,
        'isFirstLevel': False,
    }
    if data.get('children'):
        data['children'] = [_build_child_menu_with_auth(c, role_perms) for c in data['children']]
    return data


def _build_child_menu_with_auth(child_data: dict, role_perms: dict) -> dict:
    """递归构建子菜单权限信息（child_data 已是字典）"""
    available = child_data.get('permissions') or []
    granted = role_perms.get(child_data['id'], [])
    auth_list = [
        {**p, 'hasPermission': p.get('authMark') in granted}
        for p in available
    ] if available else []
    child_data['authList'] = auth_list
    child_data['hasPermission'] = True
    child_data['meta'] = {
        'title': child_data.get('title') or child_data.get('name') or '',
        'icon': child_data.get('icon') or '',
        'isEnable': child_data.get('is_visible', True),
        'keepAlive': True,
        'authList': auth_list,
        'isHide': False,
        'isHideTab': False,
        'isIframe': False,
        'isFirstLevel': False,
    }
    if child_data.get('children'):
        child_data['children'] = [_build_child_menu_with_auth(c, role_perms) for c in child_data['children']]
    return child_data


@router.get("/tree")
async def get_menu_tree(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取菜单树（按当前用户角色过滤）"""
    from app.services.role_service import RoleService

    service = MenuService(db)
    role_service = RoleService(db)

    # 按角色过滤菜单
    menus = service.get_menu_tree(role_id=current_user.role_id)
    role_perms = role_service.get_role_menu_permissions(current_user.role_id)

    return [_build_menu_with_auth(m, role_perms) for m in menus]


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
@log_audit(
    action="CREATE",
    resource_type="menu",
    get_resource_id=lambda result, kwargs: result.id if hasattr(result, 'id') else None,
    get_resource_name=lambda result, kwargs: result.name if hasattr(result, 'name') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None
)
async def create_menu(
    request: Request,
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
@log_audit(
    action="UPDATE",
    resource_type="menu",
    get_resource_id=lambda result, kwargs: kwargs.get('menu_id'),
    get_resource_name=lambda result, kwargs: result.name if hasattr(result, 'name') else None,
    get_new_values=lambda result, kwargs: result.model_dump() if hasattr(result, 'model_dump') else None
)
async def update_menu(
    request: Request,
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
@log_audit(
    action="DELETE",
    resource_type="menu",
    get_resource_id=lambda result, kwargs: kwargs.get('menu_id')
)
async def delete_menu(
    request: Request,
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
