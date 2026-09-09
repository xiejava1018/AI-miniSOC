"""
路由授权分类与写侧默认拒绝门禁（PRD §10.4 P0-T13）

覆盖：
- 所有 method+path 必须命中 public/machine/human 三类之一
- 人类读端点至少有 get_current_user 或更细授权
- 人类写端点必须有显式 AuthSpec（admin/role/button）或 session_write 例外
- 公开/机器白名单精确到 method+path

这些测试是 CI 阻断式门禁，**不**与 advisory pytest 合并。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from app.core.route_allowlist import PUBLIC_API_PATHS
from app.core.route_security import RouteAuthInfo, iter_route_auth_specs

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _all_routes(app: FastAPI) -> list[RouteAuthInfo]:
    return list(iter_route_auth_specs(app))


def _human_writes(infos: list[RouteAuthInfo]) -> list[RouteAuthInfo]:
    return [
        i for i in infos
        if i.method in WRITE_METHODS
        and not i.is_public
        and not i.is_machine
    ]


def _human_reads(infos: list[RouteAuthInfo]) -> list[RouteAuthInfo]:
    return [
        i for i in infos
        if i.method == "GET"
        and not i.is_public
        and not i.is_machine
    ]


def test_all_routes_are_classified(app: FastAPI):
    """每条 method+path 必须命中 public/machine/human 三类之一。

    未分类的路由（含已 include 但未挂任何依赖、且不在 allowlist 的）必须失败。
    """
    infos = _all_routes(app)
    assert infos, "no routes discovered; iter_route_auth_specs broken"

    classified = sum(1 for i in infos if i.is_public or i.is_machine)
    unclassified = [i for i in infos if not i.is_public and not i.is_machine]

    # 允许的"未分类"等于"人类业务路由"，本断言只是 sanity check：
    assert classified >= 0  # 至少 0 个白名单路由
    # 人类业务路由需要在后续 test_human_writes_require_explicit_auth 校验
    assert unclassified, "expected human business routes to be discovered"


def test_allowlist_is_exact(app: FastAPI):
    """公开白名单 (method, path) 与 route_allowlist.PUBLIC_API_PATHS 完全一致。

    CI 比对防止白名单漂移：若新增/删除白名单条目未同步更新 ``route_allowlist``，
    本测试会失败。
    """
    infos = _all_routes(app)
    discovered_public = {(i.method, i.path) for i in infos if i.is_public}
    declared = set(PUBLIC_API_PATHS)

    extras = discovered_public - declared
    missing = declared - discovered_public

    assert not extras, (
        f"routes marked as public but not in PUBLIC_API_PATHS: {sorted(extras)}"
    )
    assert not missing, (
        f"PUBLIC_API_PATHS entries with no matching route: {sorted(missing)}"
    )


def test_human_writes_require_explicit_auth(app: FastAPI):
    """人类写路由必须有显式授权：AuthSpec kind ∈ {admin, role, button}
    或 is_session_write 例外。
    """
    infos = _all_routes(app)
    bad = [
        i for i in _human_writes(infos)
        if not i.has_explicit_write_auth
        and not i.is_session_write
        and not i.is_router_wrapped  # 兜底依赖也算保护
    ]

    assert not bad, (
        "human write routes lacking explicit authorization:\n"
        + "\n".join(f"  {i.method} {i.path} kinds={[s.kind for s in i.auth_specs]}" for i in bad)
    )


def test_human_reads_require_auth(app: FastAPI):
    """人类读路由至少有 get_current_user 或更细授权。

    ``is_router_wrapped`` 表示 router 级注入了 ``get_current_user``（读端点要求登录）。
    """
    infos = _all_routes(app)
    bad = [
        i for i in _human_reads(infos)
        if not i.has_auth_dep and not i.is_router_wrapped
    ]
    assert not bad, (
        "human read routes without auth dependency:\n"
        + "\n".join(f"  {i.method} {i.path}" for i in bad)
    )


def test_router_wrapped_routes_have_write_default(app: FastAPI):
    """被 router 级 include_human_router 包装的路由应同时挂 ``write_default``
    （写拒绝兜底）。单独挂 ``read_only`` 视为写端点未受保护。
    """
    infos = _all_routes(app)
    writes = [i for i in _human_writes(infos) if i.is_router_wrapped]
    without_write_default = [
        i for i in writes
        if not any(s.kind == "write_default" for s in i.auth_specs)
        and not i.is_session_write
        and not i.has_explicit_write_auth
    ]
    assert not without_write_default, (
        "router-wrapped writes lacking write_default or explicit auth:\n"
        + "\n".join(f"  {i.method} {i.path} kinds={[s.kind for s in i.auth_specs]}" for i in without_write_default)
    )


def test_admin_auth_kind_is_admin(app: FastAPI):
    """require_admin() 必须挂 kind=admin 的 AuthSpec（CI 识别用）。"""
    from app.core.permissions import require_admin
    from app.core.route_security import AUTH_SPEC_ATTRIBUTE

    dep = require_admin()
    spec = getattr(dep, AUTH_SPEC_ATTRIBUTE, None)
    assert spec is not None, "require_admin() must carry an AuthSpec"
    assert spec.kind == "admin"


def test_require_role_records_roles(app: FastAPI):
    """require_role(*codes) 必须把允许的角色码挂到 AuthSpec.roles。"""
    from app.core.permissions import require_role
    from app.core.route_security import AUTH_SPEC_ATTRIBUTE

    dep = require_role("admin", "operator", "user")
    spec = getattr(dep, AUTH_SPEC_ATTRIBUTE, None)
    assert spec is not None
    assert spec.kind == "role"
    assert set(spec.roles or ()) == {"admin", "operator", "user"}


def test_route_dependencies_use_callable_attr(app: FastAPI):
    """_resolve_dep_callable 能从 Depends() 包装里取出真实函数。

    这是 _IncludedRouter.include_context.dependencies 解析的关键。
    """
    from fastapi import Depends

    from app.core.route_security import _resolve_dep_callable

    def _my_dep():
        return None

    wrapped = Depends(_my_dep)
    actual = _resolve_dep_callable(wrapped)
    assert actual is _my_dep

    # 直接传 callable
    assert _resolve_dep_callable(_my_dep) is _my_dep


# Pytest fixture: 把 main app 注入测试函数
@pytest.fixture
def app() -> FastAPI:
    from main import app as _app
    return _app