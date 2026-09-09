# src/backend/app/core/permissions.py
from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.route_security import (
    READ_ONLY_ROLES,
    AuthSpec,
    audit_denied_write,
    mark_auth_dependency,
)
from app.models.user import User


def _ensure_active(current_user: User) -> None:
    """locked/disabled 用户禁止写动作。读动作由 get_current_user 在 disabled 上抛 403。"""
    from app.models.user import UserStatus

    if current_user.status in (UserStatus.LOCKED, UserStatus.DISABLED):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"账户不可用（当前状态：{current_user.status.value}）",
        )


def require_admin() -> Callable:
    """
    要求管理员权限依赖

    用法：
        @router.get("/admin-only")
        async def admin_endpoint(
            current_user: User = Depends(require_admin())
        ):
            ...

    标记 ``AuthSpec(kind='admin')``，CI 扫描器据此识别显式授权。

    Returns:
        Callable: 校验当前用户是否为管理员的 FastAPI 依赖函数
    """
    @mark_auth_dependency(AuthSpec(kind="admin", description="require_admin"))
    async def _check_admin(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        # ORM User.is_admin 由数据库角色 code 推导而来，可信
        if not current_user.is_admin:
            audit_denied_write(
                request=request, current_user=current_user,
                reason="require_admin: not admin", db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="需要管理员权限"
            )
        _ensure_active(current_user)
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
    @mark_auth_dependency(AuthSpec(kind="menu", description=f"require_menu_permission({menu_path})"))
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
    allowed = frozenset(role_codes)

    @mark_auth_dependency(AuthSpec(
        kind="role",
        roles=tuple(sorted(allowed)),
        description=f"require_role({','.join(sorted(allowed))})",
    ))
    async def _check_role(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        if current_user.is_admin:
            return current_user
        if not current_user.role or current_user.role.code not in allowed:
            audit_denied_write(
                request=request, current_user=current_user,
                reason=f"require_role: needed {sorted(allowed)}, got {current_user.role.code if current_user.role else None}",
                db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要角色：{sorted(allowed)}",
            )
        # 角色匹配后再挡一层：只读角色不得写（写动作除 logout 外）
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            role_code = current_user.role.code if current_user.role else None
            if role_code in READ_ONLY_ROLES:
                audit_denied_write(
                    request=request, current_user=current_user,
                    reason=f"require_role: read_only_role:{role_code}", db=db,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"只读角色（{role_code}）不允许执行写操作",
                )
        _ensure_active(current_user)
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

    @mark_auth_dependency(AuthSpec(
        kind="button",
        description=f"require_button_permission({menu_path},{button})",
    ))
    async def _check_button(
        request: Request,
        current_user: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ):
        is_admin = current_user.is_admin
        has_btn = current_user.has_button_access(menu_path, button)
        if is_admin:
            return current_user
        if not has_btn:
            _log.info(
                "X1 按钮权限拒绝: user=%s menu=%s/%s (中间件会把 403 包成 200+code)",
                current_user.username, menu_path, button,
            )
            audit_denied_write(
                request=request, current_user=current_user,
                reason=f"require_button_permission: {menu_path}/{button}", db=db,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"按钮权限不足：{menu_path}/{button}",
            )
        # 按钮匹配后再挡一层：只读角色不得写
        if request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
            role_code = current_user.role.code if current_user.role else None
            if role_code in READ_ONLY_ROLES:
                audit_denied_write(
                    request=request, current_user=current_user,
                    reason=f"require_button_permission: read_only_role:{role_code}", db=db,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"只读角色（{role_code}）不允许执行写操作",
                )
        _ensure_active(current_user)
        return current_user

    return _check_button