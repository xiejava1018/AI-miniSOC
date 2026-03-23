"""
审计装饰器
用于自动记录API操作到审计日志
"""

from functools import wraps
from typing import Callable, Optional, Dict, Any
from fastapi import Request
from sqlalchemy.orm import Session

from app.services.audit_log_service import AuditLogService


def log_audit(
    action: str,
    resource_type: Optional[str] = None,
    get_resource_id: Optional[Callable] = None,
    get_resource_name: Optional[Callable] = None,
    get_old_values: Optional[Callable] = None,
    get_new_values: Optional[Callable] = None,
):
    """
    审计日志装饰器

    自动记录API操作到审计日志

    Args:
        action: 操作类型（LOGIN/LOGOUT/CREATE/UPDATE/DELETE/QUERY/EXPORT）
        resource_type: 资源类型（user/role/menu/asset/incident/alert）
        get_resource_id: 函数，用于获取资源ID
        get_resource_name: 函数，用于获取资源名称
        get_old_values: 函数，用于获取变更前的数据
        get_new_values: 函数，用于获取变更后的数据

    Usage:
        @log_audit(action="CREATE", resource_type="user")
        async def create_user(user_data: UserCreate, db: Session = Depends(get_db)):
            ...

        @log_audit(
            action="UPDATE",
            resource_type="user",
            get_resource_id=lambda kwargs: kwargs.get("user_id"),
            get_old_values=lambda result: result["old_data"],
            get_new_values=lambda result: result["new_data"]
        )
        async def update_user(user_id: int, user_data: UserUpdate, db: Session = Depends(get_db)):
            ...
    """

    def decorator(func: Callable):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # 尝试从kwargs中获取db和request
            db: Optional[Session] = kwargs.get('db')
            request: Optional[Request] = kwargs.get('request')

            # 如果没有request，尝试从args中获取（FastAPI Request对象通常是第一个参数）
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            # 如果没有db，尝试从args中获取（Depends注入的参数）
            if not db:
                for arg in args:
                    if hasattr(arg, 'query'):  # Session对象有query方法
                        db = arg
                        break

            # 执行原函数
            try:
                result = await func(*args, **kwargs)

                # 记录成功审计日志
                if db:
                    try:
                        audit_service = AuditLogService(db)

                        # 获取用户信息
                        user_id = None
                        username = "system"
                        if request and hasattr(request, 'state'):
                            user_id = getattr(request.state, 'user_id', None)
                            username = getattr(request.state, 'username', 'system')

                        # 获取资源信息
                        resource_id = None
                        resource_name = None
                        old_values = None
                        new_values = None

                        if get_resource_id:
                            resource_id = get_resource_id(result, kwargs)
                        if get_resource_name:
                            resource_name = get_resource_name(result, kwargs)
                        if get_old_values:
                            old_values = get_old_values(result, kwargs)
                        if get_new_values:
                            new_values = get_new_values(result, kwargs)

                        # 获取客户端信息
                        ip_address = None
                        user_agent = None
                        if request:
                            ip_address = request.client.host if request.client else None
                            user_agent = request.headers.get("user-agent")

                        audit_service.create_audit_log(
                            user_id=user_id,
                            username=username,
                            action=action,
                            resource_type=resource_type,
                            resource_id=resource_id,
                            resource_name=resource_name,
                            old_values=old_values,
                            new_values=new_values,
                            ip_address=ip_address,
                            user_agent=user_agent,
                            status="success"
                        )
                    except Exception as e:
                        # 审计日志记录失败不应影响业务逻辑
                        print(f"Failed to record audit log: {e}")

                return result

            except Exception as e:
                # 记录失败审计日志
                if db:
                    try:
                        audit_service = AuditLogService(db)

                        # 获取用户信息
                        user_id = None
                        username = "system"
                        if request and hasattr(request, 'state'):
                            user_id = getattr(request.state, 'user_id', None)
                            username = getattr(request.state, 'username', 'system')

                        # 获取客户端信息
                        ip_address = None
                        user_agent = None
                        if request:
                            ip_address = request.client.host if request.client else None
                            user_agent = request.headers.get("user-agent")

                        audit_service.create_audit_log(
                            user_id=user_id,
                            username=username,
                            action=action,
                            resource_type=resource_type,
                            ip_address=ip_address,
                            user_agent=user_agent,
                            status="failure",
                            error_message=str(e)
                        )
                    except Exception as audit_error:
                        # 审计日志记录失败不应影响异常抛出
                        print(f"Failed to record audit log: {audit_error}")

                # 重新抛出原始异常
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # 同步版本的包装器
            # 尝试从kwargs中获取db和request
            db: Optional[Session] = kwargs.get('db')
            request: Optional[Request] = kwargs.get('request')

            # 如果没有request，尝试从args中获取（FastAPI Request对象通常是第一个参数）
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break

            # 如果没有db，尝试从args中获取（Depends注入的参数）
            if not db:
                for arg in args:
                    if hasattr(arg, 'query'):  # Session对象有query方法
                        db = arg
                        break

            # 执行原函数
            try:
                result = func(*args, **kwargs)

                # 记录成功审计日志
                if db:
                    try:
                        audit_service = AuditLogService(db)

                        # 获取用户信息
                        user_id = None
                        username = "system"
                        if request and hasattr(request, 'state'):
                            user_id = getattr(request.state, 'user_id', None)
                            username = getattr(request.state, 'username', 'system')

                        # 获取客户端信息
                        ip_address = None
                        user_agent = None
                        if request:
                            ip_address = request.client.host if request.client else None
                            user_agent = request.headers.get("user-agent")

                        audit_service.create_audit_log(
                            user_id=user_id,
                            username=username,
                            action=action,
                            resource_type=resource_type,
                            ip_address=ip_address,
                            user_agent=user_agent,
                            status="success"
                        )
                    except Exception as e:
                        # 审计日志记录失败不应影响业务逻辑
                        print(f"Failed to record audit log: {e}")

                return result

            except Exception as e:
                # 记录失败审计日志
                if db:
                    try:
                        audit_service = AuditLogService(db)

                        # 获取用户信息
                        user_id = None
                        username = "system"
                        if request and hasattr(request, 'state'):
                            user_id = getattr(request.state, 'user_id', None)
                            username = getattr(request.state, 'username', 'system')

                        # 获取客户端信息
                        ip_address = None
                        user_agent = None
                        if request:
                            ip_address = request.client.host if request.client else None
                            user_agent = request.headers.get("user-agent")

                        audit_service.create_audit_log(
                            user_id=user_id,
                            username=username,
                            action=action,
                            resource_type=resource_type,
                            ip_address=ip_address,
                            user_agent=user_agent,
                            status="failure",
                            error_message=str(e)
                        )
                    except Exception as audit_error:
                        # 审计日志记录失败不应影响异常抛出
                        print(f"Failed to record audit log: {audit_error}")

                # 重新抛出原始异常
                raise

        # 根据函数是否是协程函数返回对应的包装器
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator
