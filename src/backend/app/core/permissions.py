# src/backend/app/core/permissions.py
from functools import wraps
from fastapi import HTTPException, status, Depends
from typing import Callable

from app.core.auth import get_current_user
from app.schemas.user import UserResponse


def require_admin() -> Callable:
    """
    要求管理员权限装饰器

    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(
            current_user: UserResponse = Depends(require_admin())
        ):
            ...
    """
    async def _check_admin(current_user: UserResponse = Depends(get_current_user)):
        # 修复: 使用 role_name 而不是 is_admin
        if current_user.role_name != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要管理员权限"
            )
        return current_user

    return _check_admin


def require_menu_permission(menu_path: str) -> Callable:
    """
    要求菜单权限装饰器

    Args:
        menu_path: 菜单路径

    Usage:
        @router.get("/system/users")
        async def get_users(
            current_user: UserResponse = Depends(require_menu_permission("system-users"))
        ):
            ...
    """
    async def _check_permission(current_user: UserResponse = Depends(get_current_user)):
        if not current_user.has_menu_access(menu_path):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限访问"
            )
        return current_user

    return _check_permission
