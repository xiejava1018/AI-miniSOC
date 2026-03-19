"""
权限检查模块
提供菜单权限检查装饰器和依赖
"""

from functools import wraps
from typing import Callable, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.auth import get_current_user
from app.schemas.user import UserResponse


security = HTTPBearer()


def require_menu_permission(required_permission: str):
    """
    FastAPI依赖装饰器：检查用户是否有特定菜单权限

    用法：
        @app.get("/api/system/users")
        async def get_users(
            current_user: UserResponse = Depends(require_menu_permission("system-users"))
        ):
            # 只有拥有"system-users"菜单权限的用户可以访问
            pass

    或者使用依赖注入：

        @app.get("/api/system/users", dependencies=[Depends(require_menu_permission("system-users"))])
        async def get_users():
            pass

    Args:
        required_permission: 所需的菜单权限标识（如 "system-users", "system-roles"）

    Returns:
        Callable: FastAPI依赖函数

    Raises:
        HTTPException: 权限不足时抛出403错误
    """

    async def check_permission(
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> UserResponse:
        """
        检查用户权限的内部函数

        Args:
            credentials: HTTP Bearer认证凭据

        Returns:
            UserResponse: 当前用户

        Raises:
            HTTPException: 权限不足时抛出403错误
        """
        # 获取当前用户
        current_user = await get_current_user(credentials)

        # TODO: 实现完整的权限检查逻辑
        # 1. 查询用户的角色
        # 2. 查询角色拥有的菜单权限
        # 3. 检查是否包含所需的菜单权限

        # 临时实现：管理员拥有所有权限
        if current_user.role_name == "admin":
            return current_user

        # 临时实现：从用户属性中检查权限（实际应从数据库查询）
        # if not hasattr(current_user, 'permissions'):
        #     raise HTTPException(
        #         status_code=status.HTTP_403_FORBIDDEN,
        #         detail=f"无权限访问此资源：需要 {required_permission} 权限"
        #     )

        # if required_permission not in current_user.permissions:
        #     raise HTTPException(
        #         status_code=status.HTTP_403_FORBIDDEN,
        #         detail=f"无权限访问此资源：需要 {required_permission} 权限"
        #     )

        # 临时实现：非管理员默认拒绝访问系统管理功能
        if required_permission.startswith("system-"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无权限访问此资源：需要 {required_permission} 权限"
            )

        return current_user

    return check_permission


class RequirePermission:
    """
    权限检查类（更灵活的权限控制）

    用法：
        @app.get("/api/system/users")
        async def get_users(
            _: UserResponse = Depends(RequirePermission("system-users"))
        ):
            pass
    """

    def __init__(self, permission: str):
        """
        初始化权限检查

        Args:
            permission: 所需的权限标识
        """
        self.permission = permission

    async def __call__(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(security)
    ) -> UserResponse:
        """
        执行权限检查

        Args:
            credentials: HTTP Bearer认证凭据

        Returns:
            UserResponse: 当前用户

        Raises:
            HTTPException: 权限不足时抛出403错误
        """
        # 使用上面的装饰器函数
        check_func = require_menu_permission(self.permission)
        return await check_func(credentials)


# 便捷权限检查装饰器（用于函数装饰）
def check_menu_permission(permission: str):
    """
    函数装饰器：检查菜单权限

    用法：
        @check_menu_permission("system-users")
        async def get_users():
            pass

    注意：FastAPI推荐使用 Depends() 而不是装饰器，
    因为装饰器无法在API文档中正确显示依赖关系

    Args:
        permission: 所需的菜单权限标识
    """

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从kwargs中获取current_user（如果存在）
            current_user = kwargs.get("current_user")

            # 如果没有current_user，进行认证
            if current_user is None:
                # 这需要请求上下文，在FastAPI中不推荐
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="需要认证"
                )

            # 检查权限
            if current_user.role_name != "admin":
                # TODO: 实现完整的权限检查
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"无权限访问此资源：需要 {permission} 权限"
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


# 常用权限常量
class Permissions:
    """权限常量定义"""

    # 系统管理权限
    SYSTEM_USERS = "system-users"
    SYSTEM_ROLES = "system-roles"
    SYSTEM_MENUS = "system-menus"
    SYSTEM_CONFIG = "system-config"
    SYSTEM_AUDIT = "system-audit"

    # 业务权限
    DASHBOARD = "dashboard"
    ASSETS_VIEW = "assets-view"
    ASSETS_MANAGE = "assets-manage"
    INCIDENTS_VIEW = "incidents-view"
    INCIDENTS_MANAGE = "incidents-manage"
    ALERTS_VIEW = "alerts-view"
    ALERTS_MANAGE = "alerts-manage"

    @classmethod
    def all_system_permissions(cls):
        """获取所有系统管理权限"""
        return [
            cls.SYSTEM_USERS,
            cls.SYSTEM_ROLES,
            cls.SYSTEM_MENUS,
            cls.SYSTEM_CONFIG,
            cls.SYSTEM_AUDIT
        ]

    @classmethod
    def all_business_permissions(cls):
        """获取所有业务权限"""
        return [
            cls.DASHBOARD,
            cls.ASSETS_VIEW,
            cls.ASSETS_MANAGE,
            cls.INCIDENTS_VIEW,
            cls.INCIDENTS_MANAGE,
            cls.ALERTS_VIEW,
            cls.ALERTS_MANAGE
        ]
