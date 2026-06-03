# src/backend/app/core/permissions.py
from functools import wraps
from fastapi import HTTPException, status, Depends
from typing import Callable

from app.core.auth import get_current_user
from app.models.user import User


def require_admin() -> Callable:
    """
    要求管理员权限依赖

    用法：
        @router.get("/admin-only")
        async def admin_endpoint(
            current_user: User = Depends(require_admin())
        ):
            ...

    Returns:
        Callable: 校验当前用户是否为管理员的 FastAPI 依赖函数
    """
    async def _check_admin(current_user: User = Depends(get_current_user)):
        # ORM User.is_admin 由数据库角色 code 推导而来，可信
        if not current_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要管理员权限"
            )
        return current_user

    return _check_admin


def require_menu_permission(menu_path: str) -> Callable:
    """
    要求菜单权限依赖

    Args:
        menu_path: 菜单路径

    用法：
        @router.get("/api/v1/users")
        async def get_users(
            current_user: User = Depends(require_menu_permission("user"))
        ):
            ...
    """
    async def _check_permission(current_user: User = Depends(get_current_user)):
        # ORM User.has_menu_access 与 Pydantic UserResponse 同名同语义
        if not current_user.has_menu_access(menu_path):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="无权限访问"
            )
        return current_user

    return _check_permission
