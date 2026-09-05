"""
测试配置和共享fixtures

> **测试库**：所有 fixture 走 ``app.core.database.test_engine``（独立 PG 库
> ``AI-miniSOC-db_test``），与生产 ``DB_NAME`` 完全隔离。运行测试前需先：
>
>     CREATE DATABASE "AI-miniSOC-db_test";
>
> 该库仅在测试期间被 ``db_session`` fixture 反复 ``create_all`` / ``drop_all``，
> 不会触碰生产数据。
"""

import os

# 测试环境：禁用 MCP SSE server（避免后台线程启 uvicorn 抢 8100 端口
# 引发 SystemExit(3) 干扰测试 session）
os.environ.setdefault("MCP_SSE_ENABLED", "false")

import pytest
from sqlalchemy.orm import Session
from typing import Generator
from fastapi.testclient import TestClient

from app.models.base import Base
from app.core.database import get_db, TestingSessionLocal, test_engine
# 注: conftest 只 import 部分 model 会导致 Base.metadata 只识别这几个表。
# pytest db_session fixture 调用 Base.metadata.create_all 时, 其他表不会被创建。
# CI 上 pytest 可能因某 test 引用未 import 的 model 而报 “表不存在”。
# 改为 import 全部 models: `from app.models import ...` 会触发 app/models/__init__.py 导入全部。
from app.models import (  # noqa: F401  (imports register all models with Base.metadata)
    User, UserStatus, Role, Menu, RoleMenu, Department, SystemConfig,
    PasswordHistory, PasswordResetToken, AuditLog, RateLimit,
    Asset, AssetPort, AssetTag, Incident, AIAnalysis, AssetIncident,
    AssetChangeLog, AssetSource, SyncTask, Dict as SysDict,
    ChatSession, ChatMessage, Notification,
    BrowsingEvent, BrowsingBlacklist, BrowsingBaseline,
    BehaviorProfile, BehaviorDomain, BehaviorProfileWatermark,
    IdentityEvent, IdentityBinding,
    AlertDigest, AlertGroupSnapshot, AlertGroupAnalysis,
    CisaKev, SocTaskRegistry, SocTaskRun,
    AssetRiskHistory, AiFeedback,
    # P3 资产扫描（docs/design/...-final.md §6.3）
    ScannerTask, ScanTarget, ScanFinding, ScannerAgent,
)
# P3：风险评分「系统健康度」维度依赖漏洞表（不在 __init__ 导出，需显式注册供 create_all）
from app.models.vulnerability import Vulnerability, AssetVulnerability, ScanTask  # noqa: F401
from main import app


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """
    创建测试数据库会话

    在独立 test_engine 上 create_all → yield → drop_all。
    不会污染生产 DB（即使测试中途崩，drop_all 失败也只影响 test_engine 本身）。
    """
    # 幂等创建；如果之前有残留表（比如上次测试崩了没 drop 完）会复用
    Base.metadata.create_all(bind=test_engine)

    session = TestingSessionLocal()

    try:
        yield session
    finally:
        session.close()
        # drop_all 只处理 Base.metadata 里的表，不会误伤 test DB 里其他对象
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def client(db_session: Session) -> TestClient:
    """
    创建测试客户端

    Args:
        db_session: 数据库会话

    Returns:
        TestClient: FastAPI测试客户端

    跳过 lifespan（不是 close-on-err shutdown）：main.py lifespan 会启5个后台
    scheduler，第一个 stop_xxx() 遇到没启的 scheduler 会返 None，
    造成 ``object NoneType can't be used in 'await' expression``。
    """
    from contextlib import asynccontextmanager
    from fastapi.testclient import TestClient

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db

    # 覆盖 lifespan 为 no-op（避免启动业务 scheduler）
    @asynccontextmanager
    async def _noop_lifespan(_app):
        yield

    app.router.lifespan_context = _noop_lifespan

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def sample_menus(db_session: Session) -> list:
    """
    Seed 一组最小可用的菜单，专门给 ``require_menu_permission`` 用。

    路径要和 ``app/api/users.py`` 实际校验的 key（"users"）一致；
    多 seed 几个常用 key（roles/menus/departments）便于后续 endpoint 测试。

    NOTE: path 故意保留复数历史值，与 ``test_role_menus_api.py`` 的
    ``Menu.path == "users"`` 断言耦合。菜单 path 单数化回归由独立的
    ``test_menu_path_singular.py`` 覆盖（自带 seed，不依赖本 fixture）。
    """
    from app.models.menu import Menu

    seed_paths = [
        ("users", "用户管理", "/system/user"),
        ("roles", "角色管理", "/system/role"),
        ("menus", "菜单管理", "/system/menu"),
        ("departments", "部门管理", "/system/department"),
        ("audit-logs", "审计日志", "/system/audit-log/index"),
    ]
    menus = []
    for path, name, component in seed_paths:
        m = Menu(path=path, name=name, component=component)
        db_session.add(m)
        menus.append(m)
    db_session.commit()
    for m in menus:
        db_session.refresh(m)
    return menus


@pytest.fixture
def sample_role(db_session: Session, sample_menus) -> Role:
    """
    创建示例角色用于测试（被 test_user / admin_user 复用，保证 FK 完整）

    默认绑定 ``sample_menus`` 里 seed 的所有菜单，方便 test_user 派生出来的
    认证 token 能通过 ``require_menu_permission(...)`` 检查。如果某个用例需要
    验证"无权限"路径，应自建一个空 role 覆盖。
    """
    from app.models.role_menu import RoleMenu

    role = Role(
        name="测试角色",
        code="test_role",
        description="用于测试的角色",
    )
    db_session.add(role)
    db_session.flush()  # 拿到 role.id

    for menu in sample_menus:
        db_session.add(RoleMenu(role_id=role.id, menu_id=menu.id, permissions=[]))

    db_session.commit()
    db_session.refresh(role)
    return role


@pytest.fixture
def test_user(db_session: Session, sample_role: Role) -> User:
    """
    创建测试用户

    Args:
        db_session: 数据库会话
        sample_role: 先建好角色，避免 role_id FK 悬空

    Returns:
        创建的测试用户
    """
    from app.core.security import get_password_hash

    user = User(
        username="testuser",
        password_hash=get_password_hash("testpass123"),
        email="test@example.com",
        full_name="Test User",
        role_id=sample_role.id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def admin_user(db_session: Session, sample_role: Role) -> User:
    """
    创建管理员用户

    Args:
        db_session: 数据库会话
        sample_role: 先建好角色

    Returns:
        创建的管理员用户
    """
    from app.core.security import get_password_hash

    user = User(
        username="admin",
        password_hash=get_password_hash("admin123"),
        email="admin@example.com",
        full_name="Admin User",
        role_id=sample_role.id,
        status=UserStatus.ACTIVE,
        is_superuser=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_token(test_user: User) -> str:
    """
    生成测试用的认证令牌（sub 必须传 user_id str，不能传 username——
    ``get_current_user`` 走 ``db.query(User).filter(User.id == int(user_id))``）
    """
    from app.core.auth import create_access_token

    return create_access_token(
        data={
            "sub": str(test_user.id),
            "username": test_user.username,
            "email": test_user.email,
            "role_id": test_user.role_id,
        }
    )


@pytest.fixture
def sample_users(db_session: Session, sample_role: Role) -> list[User]:
    """
    创建示例用户用于测试
    """
    users = []
    for i in range(5):
        user = User(
            username=f"user{i}",
            password_hash="hash",
            email=f"user{i}@example.com",
            full_name=f"Test User {i}",
            role_id=sample_role.id,
            status=UserStatus.ACTIVE,
        )
        db_session.add(user)
        users.append(user)

    db_session.commit()
    for user in users:
        db_session.refresh(user)

    return users


@pytest.fixture
def admin_token(admin_user: User) -> str:
    """
    生成管理员用的认证令牌
    """
    from app.core.auth import create_access_token

    return create_access_token(
        data={
            "sub": str(admin_user.id),
            "username": admin_user.username,
            "is_admin": True,
        }
    )


@pytest.fixture
def test_asset(db_session: Session):
    """
    创建测试资产

    Args:
        db_session: 数据库会话

    Returns:
        创建的测试资产
    """
    from app.models.asset import Asset

    asset = Asset(
        network_segment="default",
        network_zone="other",
        asset_ip="192.168.1.100",
        asset_description="测试资产",
        asset_status="在线",
        name="测试服务器",
        asset_type="server",
        criticality="normal"
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)
    return asset
