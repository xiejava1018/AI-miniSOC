"""
上网行为检测 (browsing) 路由注册完整性回归测试

背景（XIE-10 / GitHub Issue #10）：
  admin 登录后访问「行为分析」菜单下的 5 个子菜单（异常事件、行为日志、
  行为基线、黑名单管理、规则配置），页面拿到的是 HTTP 404 Not Found。

原因：
  WO-1..WO-4 权限重构（commit 6642452）把 ``api_router.include_router`` 替换为
  ``include_human_router``，但漏写了 browsing 模块——只 import 没挂载。
  所有 ``/api/v1/browsing/*`` endpoint 在生产 API router 中不存在，前端页面
  调用 404。

本测试是回归门禁：
  - 列出 browsing 模块所有 endpoint（路径 + 方法）
  - 断言它们都已注册到 ``app.api.api_router`` 下、且路径前缀为 ``/browsing``
  - 防止后续重构再次漏写

CI：与 ``test_route_authorization.py`` 一起作为阻断式门禁。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

# 期望注册到 /api/v1/browsing 前缀下的关键 endpoint（method, full_path）。
# ``iter_route_auth_specs`` 返回的 path 已包含 main.py 的 ``include_router(prefix="/api/v1")``，
# 所以完整路径形如 ``/api/v1/browsing/...``。仅覆盖 admin 登录后 5 个可见菜单
# 实际调用的接口，避免维护成本与 browsing.py 同步。
EXPECTED_BROWSING_ENDPOINTS: set[tuple[str, str]] = {
    # 异常事件（行为分析 - 异常事件）
    ("GET", "/api/v1/browsing/events"),
    ("GET", "/api/v1/browsing/events/{event_id}"),
    ("PUT", "/api/v1/browsing/events/{event_id}"),
    # 行为日志（行为分析 - 行为日志）
    ("GET", "/api/v1/browsing/logs"),
    # 行为基线（行为分析 - 行为基线）
    ("GET", "/api/v1/browsing/baseline"),
    # 黑名单管理（行为分析 - 黑名单管理）
    ("GET", "/api/v1/browsing/blacklist"),
    ("POST", "/api/v1/browsing/blacklist"),
    ("DELETE", "/api/v1/browsing/blacklist/{blacklist_id}"),
    # 规则配置（行为分析 - 规则配置）
    ("GET", "/api/v1/browsing/rules/config"),
    ("PUT", "/api/v1/browsing/rules/config"),
}


@pytest.fixture
def app() -> FastAPI:
    from main import app as _app
    return _app


def _registered_browsing_paths(app: FastAPI) -> set[tuple[str, str]]:
    """从 FastAPI app 提取所有 /api/v1/browsing 前缀的 (method, full_path) 集合。

    复用 ``iter_route_auth_specs`` 的遍历逻辑，保证与生产路由表一致。
    """
    from app.core.route_security import iter_route_auth_specs

    return {
        (info.method, info.path)
        for info in iter_route_auth_specs(app)
        if info.path.startswith("/api/v1/browsing/")
        or info.path == "/api/v1/browsing"
    }


def test_browsing_router_is_registered(app: FastAPI):
    """browsing 模块必须挂载到 api_router 下（防止 include 漏写导致 404）。"""
    registered = _registered_browsing_paths(app)
    assert registered, (
        "未发现任何 /api/v1/browsing 路由——"
        "api_router 可能漏写 include_human_router(api_router, browsing.router, ...)"
    )


def test_browsing_endpoints_match_admin_visible_menus(app: FastAPI):
    """admin 行为分析菜单下 5 个页面用到的 endpoint 全部可见。

    一旦发现缺失，立即报告具体的 (method, path)，便于排错。
    """
    registered = _registered_browsing_paths(app)
    missing = EXPECTED_BROWSING_ENDPOINTS - registered
    assert not missing, (
        "以下 browsing endpoint 未注册到 api_router，"
        "admin 行为分析菜单点击后必现 404：\n"
        + "\n".join(f"  {m} {p}" for m, p in sorted(missing))
    )


def test_browsing_router_imported_in_api_init():
    """静态检查：browsing 模块必须被 api/__init__.py import。

    防止从 import 列表中被删除（无 import 就不可能 include 注册）。
    """
    import os
    import app.api as api_pkg  # noqa: F401  (load the package so __path__ resolves)

    init_path = os.path.join(api_pkg.__path__[0], "__init__.py")  # type: ignore[index]
    with open(init_path, encoding="utf-8") as fh:
        source = fh.read()

    assert "browsing" in source, (
        "app/api/__init__.py 未 import browsing 模块，"
        "include_human_router(api_router, browsing.router, ...) 无效"
    )
