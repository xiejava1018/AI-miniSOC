# src/backend/app/core/permissions.py
from functools import wraps
from fastapi import HTTPException, status, Depends
from typing import Callable

from app.core.auth import get_current_user
from app.models.user import User
from app.models.role import RoleCode


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


def require_role(*role_codes: str) -> Callable:
    """
    要求指定角色依赖（PRD X1 权限矩阵）。

    admin 始终放行，其余枚举 role_codes 限定接受范围。
    与 require_menu_permission 的区别：后者限制菜单可见性，
    本依赖限制业务操作权限。

    用法：
        @router.post("/reports/generate")
        async def generate(
            current_user: User = Depends(require_role("admin", "operator"))
        ):
            ...
    """
    allowed = set(role_codes)

    async def _check_role(current_user: User = Depends(get_current_user)):
        if current_user.is_admin:
            return current_user
        if not current_user.role or current_user.role.code not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要角色：{sorted(allowed)}",
            )
        return current_user

    return _check_role


def require_button_permission(menu_path: str, button: str) -> Callable:
    """
    要求菜单按钮权限依赖（PRD X1）。

    底层读 RoleMenu.permissions JSONB 数组。
    admin bypass。检查 'authMark' 是否在当前菜单的权限列表中。

    用法：
        @router.post("/assets/reconcile")
        async def trigger_reconcile(
            current_user: User = Depends(require_button_permission(
                "/asset/reconciliation", "reconcile"
            ))
        ):
            ...
    """
    import logging
    _log = logging.getLogger("permissions")

    async def _check_button(current_user: User = Depends(get_current_user)):
        is_admin = current_user.is_admin
        has_btn = current_user.has_button_access(menu_path, button)
        if is_admin:
            return current_user
        if not has_btn:
            _log.info(
                "X1 按钮权限拒绝: user=%s menu=%s/%s (中间件会把 403 包成 200+code)",
                current_user.username, menu_path, button,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"按钮权限不足：{menu_path}/{button}",
            )
        return current_user

    return _check_button
