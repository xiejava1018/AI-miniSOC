"""
路由级安全分类与写侧默认拒绝

实现 PRD §10.1 的路由安全规格：
- 每个写入路由（POST/PUT/PATCH/DELETE）必须挂带 ``AuthSpec`` 的显式授权依赖
  （``require_admin`` / ``require_role`` / ``require_button_permission``），
  否则被默认拒绝。
- ``viewer`` / ``readonly`` 任何业务写操作一律拒绝（除了 ``/auth/logout``）。
- 拒绝动作写入 ``soc_audit_logs``。

设计要点：
- ``AuthSpec`` 是依赖函数上的 Python attribute；CI 扫描器只读 attribute，
  不依赖框架内部结构，兼容任何 ``include_router`` 写法。
- ``enforce_write_default`` 是集中式兜底，写端点若未挂授权依赖即被它拦下；
  即使个别端点忘了写，也不会被静默放行。
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.user import User, UserStatus

_log = logging.getLogger("route_security")


# ---------------------------------------------------------------------------
# AuthSpec：每个授权依赖上挂的机器可识别元数据
# ---------------------------------------------------------------------------

AUTH_SPEC_ATTRIBUTE = "__auth_spec__"


@dataclass(frozen=True)
class AuthSpec:
    """授权依赖的机器可识别标记。

    Attributes:
        kind: 授权原语类别，用于 CI 报告与审计（admin/role/button/session_write/public）。
        roles: 显式允许的角色码。``None`` 表示"不绑定具体角色"（如 admin bypass）。
        allows_session_write: True 表示这是 ``/auth/logout`` 之类的会话写例外，
            即便用户是 viewer 也放行。
        description: 可选描述，给 CI 报告使用。
    """

    kind: str
    roles: tuple[str, ...] | None = None
    allows_session_write: bool = False
    description: str | None = None


def mark_auth_dependency(spec: AuthSpec) -> Callable[[Any], Any]:
    """装饰器：把 ``AuthSpec`` 挂到依赖工厂返回的 async function 上。

    用法::

        def require_role(*codes):
            allowed = set(codes)
            async def _check(current_user=Depends(get_current_user)):
                ...
            mark_dependency = mark_auth_dependency(AuthSpec(
                kind="role", roles=tuple(sorted(allowed)),
            ))
            return mark_dependency(_check)

    CI 通过 ``inspect`` 依赖树时，会优先看 ``__auth_spec__`` 元数据；找不到元数据
    但函数本身已挂 ``Depends(get_current_user)`` 兜底（读端点），仍视为有效授权。
    """

    def _wrap(dep_callable: Callable[[Any], Any]) -> Callable[[Any], Any]:
        try:
            setattr(dep_callable, AUTH_SPEC_ATTRIBUTE, spec)
        except (AttributeError, TypeError):
            # 某些 callable 不支持 setattr（极端情况），记录后跳过
            _log.warning(
                "Cannot attach AuthSpec to dependency %r; dependency type does not support setattr",
                dep_callable,
            )
        return dep_callable

    return _wrap


def get_auth_spec(dep: Any) -> AuthSpec | None:
    """读取依赖上的 AuthSpec；不存在则返回 None。"""
    if dep is None:
        return None
    return getattr(dep, AUTH_SPEC_ATTRIBUTE, None)


# ---------------------------------------------------------------------------
# 角色集合常量（与 PRD §10.0 对齐）
# ---------------------------------------------------------------------------

# 视为只读角色的集合：viewer / readonly / auditor（auditor 只读业务与审计日志）
# readonly 虽停用，但旧 token 存量期内仍须硬拒绝写
READ_ONLY_ROLES: frozenset[str] = frozenset({"viewer", "readonly", "auditor"})

# 业务写角色：admin 由 is_admin bypass；operator/user 走显式 require_role 校验
BUSINESS_WRITE_ROLES: frozenset[str] = frozenset({"operator", "user"})

# 系统管理角色：仅 admin；user/operator/viewer/auditor 一律 403
SYSTEM_ADMIN_ROLES: frozenset[str] = frozenset({"admin"})


# ---------------------------------------------------------------------------
# 写侧默认拒绝（兜底依赖）
# ---------------------------------------------------------------------------


async def enforce_write_default(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """默认写保护：viewer/readonly 任何写操作一律拒绝。

    注意：本依赖**只能用作兜底**——若路由同时挂了更精细的 ``require_role``
    /``require_button_permission``/``require_admin``，会优先由它们完成校验并
    通过。本函数仅在路由未声明其他授权时执行。

    设计上把 viewer/readonly 写拒绝放在最严的一档（即使忘了挂更精细的授权，
    也不至于让只读账号写得了）。其他角色的"业务写"由显式 ``require_role``
    负责——这是 WO-2 的核心翻转："不声明 = 拒绝"。

    状态处理：
    - ``LOCKED`` / ``DISABLED`` 用户任何写都直接 403（与现有 ``get_current_user``
      在 DISABLED 上抛 403 一致，LOCKED 这里也升级为 403，与 AC-1 对齐）。
    """
    method = request.method.upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        # 非写方法不在本兜底范围；读保护由 router-level get_current_user 负责
        return current_user

    if current_user.status in (UserStatus.LOCKED, UserStatus.DISABLED):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"账户不可用（当前状态：{current_user.status.value}）",
        )

    role_code = current_user.role.code if current_user.role else None
    if role_code in READ_ONLY_ROLES:
        # 审计：viewer/readonly/auditor 写尝试。
        # 使用请求主 db session（依赖注入），与生产/test DB 一致；
        # 同时调用 rollback 以免在请求会话上残留事务。
        try:
            audit_denied_write(
                request=request, current_user=current_user,
                reason=f"read_only_role:{role_code}", db=db,
            )
        except Exception as exc:  # noqa: BLE001 - 审计失败必须 swallow
            _log.warning("audit_denied_write failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"只读角色（{role_code}）不允许执行写操作",
        )

    return current_user


async def require_session_write(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> User:
    """会话写例外：仅用于 ``POST /auth/logout``，所有已登录用户（含 viewer）均允许。

    任何 viewer/readonly 业务写仍被 ``enforce_write_default`` 拦截——logout 不属于
    业务写，是会话管理动作。
    """
    if current_user.status in (UserStatus.LOCKED, UserStatus.DISABLED):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"账户不可用（当前状态：{current_user.status.value}）",
        )
    return current_user


# 把这两个工厂自身挂上 AuthSpec，让它们被其它授权依赖替换时也能被 CI 识别。
mark_auth_dependency(AuthSpec(kind="write_default", description="enforce_write_default"))(enforce_write_default)
mark_auth_dependency(AuthSpec(kind="session_write", allows_session_write=True, description="auth/logout 例外"))(require_session_write)


# ---------------------------------------------------------------------------
# 拒绝审计（写侧默认拒绝 + require_* 失败）
# ---------------------------------------------------------------------------


async def _audit_write_denial(
    *,
    request: Request,
    current_user: User,
    reason: str,
    db: Session | None = None,
) -> None:
    """写拒绝审计：viewer/readonly 默认拒绝时调用。

    使用独立 Session 写入，避免污染请求主 session。审计失败绝不阻塞授权决定。
    """
    try:
        from app.services.audit_log_service import AuditLogService

        if db is None:
            # 兜底：用一个短生命周期 session 落审计
            from app.core.database import SessionLocal

            db = SessionLocal()
            own_session = True
        else:
            own_session = False

        try:
            client_ip = request.client.host if request.client else None
            user_agent = request.headers.get("user-agent")
            service = AuditLogService(db)
            service.create_audit_log(
                user_id=current_user.id,
                username=current_user.username,
                action="WRITE_DENIED",
                resource_type="route",
                resource_id=None,
                resource_name=f"{request.method} {request.url.path}",
                ip_address=client_ip,
                user_agent=user_agent,
                status="failure",
                error_message=reason,
            )
            db.commit()
        finally:
            if own_session:
                db.close()
    except Exception as exc:  # noqa: BLE001 - 审计失败必须 swallow
        _log.warning("审计写入失败（不影响授权决定）: %s", exc)


def audit_denied_write(
    *,
    request: Request,
    current_user: User,
    reason: str,
    db: Session,
) -> None:
    """同步场景下的拒绝审计；写入失败仅记录日志，绝不抛。"""
    try:
        from app.services.audit_log_service import AuditLogService

        client_ip = request.client.host if request.client else None
        user_agent = request.headers.get("user-agent")
        service = AuditLogService(db)
        service.create_audit_log(
            user_id=current_user.id,
            username=current_user.username,
            action="WRITE_DENIED",
            resource_type="route",
            resource_id=None,
            resource_name=f"{request.method} {request.url.path}",
            ip_address=client_ip,
            user_agent=user_agent,
            status="failure",
            error_message=reason,
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        _log.warning("审计写入失败（不影响授权决定）: %s", exc)


# ---------------------------------------------------------------------------
# 路由扫描：CI 用，从 FastAPI app 枚举出每个 method+path 的授权分类
# ---------------------------------------------------------------------------


@dataclass
class RouteAuthInfo:
    """扫描得到的某条路由的授权元数据。

    Attributes:
        method: HTTP 方法（大写）
        path: OpenAPI 风格路径（含 ``{user_id}`` 等占位符）
        path_regex: Starlette 编译后的 path regex（用于精确匹配）
        has_auth_dep: 是否至少有 ``Depends(get_current_user)`` 或显式授权
        has_explicit_write_auth: 是否有带 AuthSpec 的显式写授权依赖
        is_session_write: 是否属于 ``/auth/logout`` 之类的会话写例外
        is_public: 是否在公开白名单内
        is_machine: 是否属于机器通道（API Key/Webhook 等）
        is_router_wrapped: 是否被 ``include_human_router`` 包装过（含默认写拒绝）
        auth_specs: 找到的所有 AuthSpec
        depends: 该路由直接挂的依赖列表（来自 FastAPI route.dependant.dependencies）
        error: 扫描过程中遇到的错误（如依赖未挂 spec）
    """

    method: str
    path: str
    path_regex: Any = None
    has_auth_dep: bool = False
    has_explicit_write_auth: bool = False
    is_session_write: bool = False
    is_public: bool = False
    is_machine: bool = False
    is_router_wrapped: bool = False
    auth_specs: list[AuthSpec] = field(default_factory=list)
    depends: list[Any] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "method": self.method,
            "path": self.path,
            "has_auth_dep": self.has_auth_dep,
            "has_explicit_write_auth": self.has_explicit_write_auth,
            "is_session_write": self.is_session_write,
            "is_public": self.is_public,
            "is_machine": self.is_machine,
            "is_router_wrapped": self.is_router_wrapped,
            "auth_spec_kinds": [s.kind for s in self.auth_specs],
            "error": self.error,
        }


def iter_route_auth_specs(app) -> Iterable[RouteAuthInfo]:
    """遍历 FastAPI app 的所有路由，返回 ``RouteAuthInfo`` 流。

    本函数是 CI 的主要数据源。它递归遍历 ``app.routes``（含 ``_IncludedRouter``），
    兼容 Starlette 与 FastAPI 的嵌套结构。
    """
    from app.core.route_allowlist import PUBLIC_API_PATHS

    public_paths = {(m.upper(), p) for m, p in PUBLIC_API_PATHS}

    yield from _iter_routes(app.routes, prefix="", public_paths=public_paths, inherited_router_deps=[])


def _iter_routes(
    routes,
    prefix: str,
    public_paths: set,
    inherited_router_deps: list[Any],
) -> Iterable[RouteAuthInfo]:
    """递归遍历 FastAPI/Starlette 路由树，yield 每条 method+path。

    Args:
        routes: 当前层路由列表
        prefix: 拼接到的路径前缀（与本层路由 path 拼成完整 OpenAPI 路径）
        public_paths: 公开白名单 method+path 集合
        inherited_router_deps: 从上层 _IncludedRouter.include_context.dependencies 传递下来的依赖
    """
    from fastapi.routing import APIRoute
    from starlette.routing import Route as StarletteRoute

    # 首次进入时给 get_current_user 挂 AuthSpec
    _ensure_get_current_user_marked()

    for route in routes:
        cls_name = type(route).__name__

        if cls_name == "_IncludedRouter":
            # FastAPI 子路由挂载：prefix 在 include_context.prefix 上
            ctx = getattr(route, "include_context", None)
            sub_prefix = getattr(ctx, "prefix", "") if ctx else ""
            # original_router.routes 是原始子路由列表
            sub_routes = getattr(getattr(route, "original_router", None), "routes", None) or []
            # 合并：父 prefix + 子 prefix
            full_prefix = prefix + (sub_prefix or "")
            # 关键：include_context.dependencies 是 router 级 dependencies
            router_deps = list(getattr(ctx, "dependencies", []) or []) if ctx else []
            child_inherited = inherited_router_deps + router_deps
            yield from _iter_routes(sub_routes, full_prefix, public_paths, child_inherited)
            continue

        if isinstance(route, APIRoute):
            # APIRoute.path 是 OpenAPI 风格（含 {user_id}），与 include_router 的 prefix 拼接
            openapi_path = prefix + route.path

            methods = {m.upper() for m in route.methods or set()}
            for method in methods:
                if method in {"HEAD"}:
                    continue
                yield from _build_route_info(
                    route, method, openapi_path, public_paths,
                    inherited_router_deps=inherited_router_deps,
                )
        elif isinstance(route, StarletteRoute):
            # FastAPI 在主 app 上挂载的 docs/openapi/redoc 是 Starlette Route，
            # 它们不出现在 api_router 内。仅用于发现公开白名单中的固定路径。
            openapi_path = prefix + (route.path or "")
            methods = {m.upper() for m in (route.methods or set())}
            for method in methods:
                if method in {"HEAD"}:
                    continue
                info = RouteAuthInfo(method=method, path=openapi_path)
                if (method, openapi_path) in public_paths:
                    info.is_public = True
                    info.auth_specs.append(AuthSpec(kind="public"))
                else:
                    info.is_machine = True
                    info.auth_specs.append(AuthSpec(kind="machine"))
                yield info
        else:
            # Starlette Mount / Route
            sub_prefix = prefix + getattr(route, "path", "")
            sub_routes = getattr(route, "routes", None)
            if sub_routes:
                yield from _iter_routes(sub_routes, sub_prefix, public_paths, inherited_router_deps)


def _build_route_info(
    route, method: str, openapi_path: str, public_paths: set,
    inherited_router_deps: list[Any] | None = None,
) -> Iterable[RouteAuthInfo]:
    """构造单条路由的 RouteAuthInfo。"""
    from app.core.route_allowlist import MACHINE_API_PREFIXES

    info = RouteAuthInfo(method=method, path=openapi_path)

    # 公开白名单（method+path 精确匹配）
    if (method, openapi_path) in public_paths:
        info.is_public = True
        info.auth_specs.append(AuthSpec(kind="public"))
        yield info
        return

    # 机器通道（前缀匹配）
    from app.core.route_allowlist import is_scanner_callback
    if any(openapi_path.startswith(p) for p in MACHINE_API_PREFIXES) or is_scanner_callback(openapi_path):
        info.is_machine = True
        info.auth_specs.append(AuthSpec(kind="machine"))
        yield info
        return

    # 人类业务路由：递归遍历 FastAPI Dependant 树，收集所有 AuthSpec
    dependant = getattr(route, "dependant", None)
    auth_specs: list[AuthSpec] = []
    callables_seen: list[Any] = []

    if dependant is not None:
        _collect_auth_specs(dependant, auth_specs, callables_seen)
    # 路由自身属性 dependencies（兼容未来 include_router 加的）
    for router_dep in getattr(route, "dependencies", []) or []:
        actual = _resolve_dep_callable(router_dep)
        spec = get_auth_spec(actual)
        if spec is not None:
            auth_specs.append(spec)
        callables_seen.append(actual)
    # 父 _IncludedRouter 的 router 级 dependencies（如 include_human_router 注入的）
    for dep in (inherited_router_deps or []):
        actual = _resolve_dep_callable(dep)
        if actual in callables_seen:
            continue
        callables_seen.append(actual)
        spec = get_auth_spec(actual)
        if spec is not None and spec not in auth_specs:
            auth_specs.append(spec)

    info.depends = callables_seen
    info.auth_specs = auth_specs
    info.has_auth_dep = any(
        s.kind in {"read_only", "admin", "role", "button", "menu"} for s in auth_specs
    )
    info.has_explicit_write_auth = any(
        s.kind in {"admin", "role", "button"} for s in auth_specs
    )
    info.is_session_write = any(s.allows_session_write for s in auth_specs)
    info.is_router_wrapped = _has_router_wrapped_security(auth_specs)
    yield info


def _collect_auth_specs(dependant, auth_specs: list[AuthSpec], callables_seen: list[Any]) -> None:
    """递归遍历 FastAPI Dependant 树，收集每个 callable 的 AuthSpec。

    Dependant 是 FastAPI 的内部依赖描述对象；每个 ``dependencies`` 元素本身
    也是 ``Dependant``，其 ``call`` 字段是真实的依赖函数（可能与 ``Depends(callable)``
    包装后指向同一函数）。
    """
    if dependant is None:
        return
    call = getattr(dependant, "call", None)
    if call is not None and call not in callables_seen:
        callables_seen.append(call)
        spec = get_auth_spec(call)
        if spec is not None and spec not in auth_specs:
            auth_specs.append(spec)

    for sub in getattr(dependant, "dependencies", []) or []:
        _collect_auth_specs(sub, auth_specs, callables_seen)


def _resolve_dep_callable(dep: Any) -> Any:
    """从 Starlette/FastAPI Depends 包装中取出真实依赖函数。

    兼容多个版本：
    - ``Depends(callable=...)`` → ``.dependency``（新版字段）
    - ``Depends(callable=...)`` → ``.callable``（旧版字段）
    - 直接传 callable 时透传
    """
    if dep is None:
        return None
    actual = getattr(dep, "callable", None)
    if actual is None:
        actual = getattr(dep, "dependency", None)
    if actual is None:
        actual = dep
    return actual


def _has_router_wrapped_security(auth_specs: list[AuthSpec]) -> bool:
    """是否由 router 级 ``include_human_router`` 包装了默认鉴权与默认写拒绝。

    识别依据：``get_current_user`` 与 ``enforce_write_default`` 都会挂 AuthSpec
    （前者 kind 为 ``read_only``，后者 kind 为 ``write_default``）。
    """
    kinds = {s.kind for s in auth_specs}
    return "write_default" in kinds or "read_only" in kinds


def _is_get_current_user(callable_obj: Any) -> bool:
    """弱判别：函数名/引用是否指向 ``get_current_user``。

    不做严格的 ``is`` 比对（依赖工厂可能包装一层），只看模块路径与名字。
    """
    if callable_obj is None:
        return False
    name = getattr(callable_obj, "__name__", "")
    module = getattr(callable_obj, "__module__", "")
    if name == "get_current_user" and module.endswith("auth"):
        return True
    # 兼容 require_active_user 等包裹层
    return name == "get_current_user" and module.startswith("app.core.auth")


def _ensure_get_current_user_marked() -> None:
    """给 ``app.core.auth.get_current_user`` 挂上 AuthSpec（kind=read_only）。

    为避免循环导入（route_security -> auth -> route_security），
    采用运行期 lazy attach：首次调用此函数时动态 import 并标记。
    """
    from app.core.auth import get_current_user
    if getattr(get_current_user, AUTH_SPEC_ATTRIBUTE, None) is None:
        try:
            mark_auth_dependency(AuthSpec(kind="read_only", description="get_current_user"))(get_current_user)
        except (AttributeError, TypeError):
            pass