# tests/integration/test_users_me_api.py
"""
用户中心自助端点 + MCP Key 管理 API 集成测试（PR1 Agent B）。

覆盖设计文档 §4.1 全部端点与 §4.3 校验规则、§7 权限矩阵：
- GET/PUT /users/me（白名单 422 / 正常更新）
- POST /users/me/change-password（401/422/429 锁定/成功审计）
- /users/me/mcp-keys 五端点（一次性明文/409 重复与超限/viewer 403/延期/幂等注销）
- /users/{user_id}/mcp-keys admin 三端点（403 非 admin/代发/强制注销/404）
- 路由顺序：/me 未被 /{user_id} 吞掉（所有 /me 用例隐式回归）

envelope 约定：HTTP 恒 200，业务码在 body.code（CLAUDE.md §1.1）。
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

import app.api.users as users_api
from app.core.auth import create_access_token
from app.core.security import get_password_hash, verify_password
from app.models import AuditLog, Role, User, UserStatus
from app.models.base import Base
from app.models.department import Department
from app.models.menu import Menu
from app.models.mcp_key import SOCMCPKey
from app.models.role_menu import RoleMenu
from app.models.user_session import UserSession


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------

# 本模块用受限表集合建/删表（而非全量 Base.metadata）：
# 当前 venv 的 SQLAlchemy 2.0.54 对全量 metadata 的 create_all 存在重复
# CREATE TYPE 问题（存量环境问题，与 test_users_api.py 无关，验证过可复现），
# 且全量建 130+ 张表对本模块纯属浪费。闭包：users/roles/departments/
# role_menus/menus/audit_logs/mcp_keys 七张表覆盖全部 FK 依赖。
_TEST_TABLES = [
    User.__table__, Role.__table__, Department.__table__,
    Menu.__table__, RoleMenu.__table__,
    UserSession.__table__,   # soc_audit_logs.session_id FK 指向它
    AuditLog.__table__, SOCMCPKey.__table__,
]


@pytest.fixture
def db_session():
    """覆盖 conftest 同名 fixture：受限表集 + 每用例隔离。"""
    from app.core.database import TestingSessionLocal, test_engine

    Base.metadata.create_all(bind=test_engine, tables=_TEST_TABLES)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine, tables=_TEST_TABLES)

@pytest.fixture(autouse=True)
def _reset_pwd_change_attempts():
    """改密失败计数是模块级 in-memory 状态，测试间必须清零隔离。"""
    users_api._pwd_change_attempts.clear()
    yield
    users_api._pwd_change_attempts.clear()


def _make_token(user: User) -> str:
    """与 conftest.auth_token 同构：sub 必须是 user_id 的字符串。"""
    return create_access_token(data={
        "sub": str(user.id),
        "username": user.username,
        "role_id": user.role_id,
    })


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def viewer_user(db_session: Session) -> User:
    """只读角色用户（role.code=viewer，自助申请 MCP Key 应 403）。"""
    role = Role(name="只读角色", code="viewer", description="viewer 测试角色")
    db_session.add(role)
    db_session.flush()
    user = User(
        username="viewer1",
        password_hash=get_password_hash("viewerpass1"),
        email="viewer1@example.com",
        role_id=role.id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def one_key(client: TestClient, auth_token: str) -> dict:
    """预置一个 active Key（name=workbuddy, 90 天），供延期/注销用例复用。"""
    resp = client.post(
        "/api/v1/users/me/mcp-keys",
        json={"name": "workbuddy", "validity_days": 90},
        headers=_auth(auth_token),
    )
    assert resp.json()["code"] == 200
    return resp.json()["data"]


# ---------------------------------------------------------------------------
# GET/PUT /users/me
# ---------------------------------------------------------------------------

def test_get_me_unauthorized(client: TestClient):
    resp = client.get("/api/v1/users/me")
    body = resp.json()
    assert resp.status_code == 200
    assert body["code"] in (401, 403)


def test_get_me_profile(client: TestClient, auth_token: str, test_user: User):
    resp = client.get("/api/v1/users/me", headers=_auth(auth_token))
    body = resp.json()
    assert body["code"] == 200
    data = body["data"]
    assert data["username"] == "testuser"
    assert data["role_code"] == "test_role"      # 完整字段：比 /auth/me 多 role_code
    assert data["department_name"] is None
    assert "id" in data and "created_at" in data


def test_put_me_update_fields(client: TestClient, auth_token: str):
    resp = client.put(
        "/api/v1/users/me",
        json={"nick_name": "新昵称", "phone": "13800000000", "gender": 1},
        headers=_auth(auth_token),
    )
    assert resp.json()["code"] == 200
    data = resp.json()["data"]
    assert data["nick_name"] == "新昵称"
    assert data["phone"] == "13800000000"
    assert data["gender"] == 1

    # 持久化验证
    resp2 = client.get("/api/v1/users/me", headers=_auth(auth_token))
    assert resp2.json()["data"]["nick_name"] == "新昵称"


def test_put_me_forbidden_fields(client: TestClient, auth_token: str):
    """越权字段（username/role_id）→ 422，且 detail 指明字段名。"""
    resp = client.put(
        "/api/v1/users/me",
        json={"nick_name": "x", "username": "hacker", "role_id": 1},
        headers=_auth(auth_token),
    )
    body = resp.json()
    assert body["code"] == 422
    assert "username" in body["msg"] and "role_id" in body["msg"]


def test_put_me_invalid_gender(client: TestClient, auth_token: str):
    resp = client.put(
        "/api/v1/users/me",
        json={"gender": 9},
        headers=_auth(auth_token),
    )
    assert resp.json()["code"] == 422


# ---------------------------------------------------------------------------
# POST /users/me/change-password
# ---------------------------------------------------------------------------

def test_change_password_wrong_old(client: TestClient, auth_token: str):
    resp = client.post(
        "/api/v1/users/me/change-password",
        json={"old_password": "wrong-old-1", "new_password": "newpass123"},
        headers=_auth(auth_token),
    )
    assert resp.json()["code"] == 401


def test_change_password_weak_new(client: TestClient, auth_token: str):
    resp = client.post(
        "/api/v1/users/me/change-password",
        json={"old_password": "testpass123", "new_password": "123"},
        headers=_auth(auth_token),
    )
    assert resp.json()["code"] == 422


def test_change_password_success(client: TestClient, auth_token: str, db_session: Session, test_user: User):
    resp = client.post(
        "/api/v1/users/me/change-password",
        json={"old_password": "testpass123", "new_password": "brand-new-pass-9"},
        headers=_auth(auth_token),
    )
    assert resp.json()["code"] == 200

    db_session.refresh(test_user)
    assert verify_password("brand-new-pass-9", test_user.password_hash)
    assert not verify_password("testpass123", test_user.password_hash)

    # 审计链：password.change.success（§4.3 R5）
    rows = db_session.query(AuditLog).filter(
        AuditLog.action == "password.change.success", AuditLog.user_id == test_user.id
    ).all()
    assert len(rows) == 1


def test_change_password_lockout(client: TestClient, auth_token: str):
    """连续 5 次旧密码错误 → 第 5 次起 429 锁定。"""
    payload = {"old_password": "bad-old-pass", "new_password": "newpass123"}
    codes = []
    for _ in range(6):
        resp = client.post(
            "/api/v1/users/me/change-password", json=payload, headers=_auth(auth_token)
        )
        codes.append(resp.json()["code"])
    assert codes[:4] == [401, 401, 401, 401]
    assert codes[4] == 429 and codes[5] == 429


def test_change_password_fail_audited(client: TestClient, auth_token: str, db_session: Session, test_user: User):
    client.post(
        "/api/v1/users/me/change-password",
        json={"old_password": "nope-1", "new_password": "newpass123"},
        headers=_auth(auth_token),
    )
    rows = db_session.query(AuditLog).filter(
        AuditLog.action == "password.change.fail", AuditLog.user_id == test_user.id
    ).all()
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# /users/me/mcp-keys（自助）
# ---------------------------------------------------------------------------

def test_list_my_keys_empty(client: TestClient, auth_token: str):
    resp = client.get("/api/v1/users/me/mcp-keys", headers=_auth(auth_token))
    body = resp.json()
    assert body["code"] == 200
    assert body["data"] == []


def test_create_mcp_key_roundtrip(client: TestClient, auth_token: str, db_session: Session, test_user: User):
    """申请 → 一次性明文返回 → 列表只见前缀不见明文 → 审计只记前缀。"""
    resp = client.post(
        "/api/v1/users/me/mcp-keys",
        json={"name": "workbuddy", "validity_days": 90},
        headers=_auth(auth_token),
    )
    body = resp.json()
    assert body["code"] == 200
    created = body["data"]
    assert created["key"].startswith("sk-mcp-")
    assert created["key_prefix"] == created["key"][:11]
    assert created["status"] == "active"
    assert 80 <= created["days_remaining"] <= 90

    # 列表：无明文字段
    lst = client.get("/api/v1/users/me/mcp-keys", headers=_auth(auth_token)).json()["data"]
    assert len(lst) == 1
    assert "key" not in lst[0]
    assert lst[0]["key_prefix"] == created["key_prefix"]

    # 审计链：mcp_key.create 落链。
    # 注：@log_audit 装饰器从 request.state 取用户，而全项目无中间件设置
    # request.state.user_id（存量行为），故审计行 user_id=None/username=system。
    rows = db_session.query(AuditLog).filter(
        AuditLog.action == "mcp_key.create"
    ).all()
    assert len(rows) == 1
    import json
    new_values_dump = json.dumps(rows[0].new_values or {}, default=str)
    assert created["key"] not in new_values_dump          # 明文永不落审计链（设计 §8）
    assert created["key_prefix"] in new_values_dump       # 只记前缀


def test_create_mcp_key_duplicate_name(client: TestClient, auth_token: str, one_key: dict):
    resp = client.post(
        "/api/v1/users/me/mcp-keys",
        json={"name": "workbuddy", "validity_days": 30},
        headers=_auth(auth_token),
    )
    assert resp.json()["code"] == 409


def test_create_mcp_key_over_cap(client: TestClient, auth_token: str, one_key: dict):
    """max_per_user=5（契约默认）：第 6 个 → 409。"""
    for i in range(4):  # 已有 1 个，再补 4 个到 5
        resp = client.post(
            "/api/v1/users/me/mcp-keys",
            json={"name": f"key-{i}", "validity_days": 7},
            headers=_auth(auth_token),
        )
        assert resp.json()["code"] == 200
    resp = client.post(
        "/api/v1/users/me/mcp-keys",
        json={"name": "sixth", "validity_days": 7},
        headers=_auth(auth_token),
    )
    assert resp.json()["code"] == 409


def test_create_mcp_key_viewer_forbidden(client: TestClient, viewer_user: User):
    """viewer 角色 → 403（设计 §7，需 admin 代发）。"""
    resp = client.post(
        "/api/v1/users/me/mcp-keys",
        json={"name": "viewer-key", "validity_days": 7},
        headers=_auth(_make_token(viewer_user)),
    )
    assert resp.json()["code"] == 403


def test_viewer_can_still_list_own_keys(client: TestClient, viewer_user: User):
    """查看自己的 Key 列表对所有角色开放（设计 §7）。"""
    resp = client.get(
        "/api/v1/users/me/mcp-keys", headers=_auth(_make_token(viewer_user))
    )
    assert resp.json()["code"] == 200


def test_extend_key(client: TestClient, auth_token: str, one_key: dict):
    resp = client.post(
        f"/api/v1/users/me/mcp-keys/{one_key['id']}/extend",
        json={"new_validity_days": 30},
        headers=_auth(auth_token),
    )
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["days_remaining"] <= 30


def test_extend_revoked_key_conflict(client: TestClient, auth_token: str, one_key: dict):
    client.delete(f"/api/v1/users/me/mcp-keys/{one_key['id']}", headers=_auth(auth_token))
    resp = client.post(
        f"/api/v1/users/me/mcp-keys/{one_key['id']}/extend",
        json={"new_validity_days": 30},
        headers=_auth(auth_token),
    )
    assert resp.json()["code"] == 409


def test_revoke_key_idempotent(client: TestClient, auth_token: str, one_key: dict):
    r1 = client.delete(f"/api/v1/users/me/mcp-keys/{one_key['id']}", headers=_auth(auth_token))
    r2 = client.delete(f"/api/v1/users/me/mcp-keys/{one_key['id']}", headers=_auth(auth_token))
    assert r1.json()["code"] == 200 and r2.json()["code"] == 200
    assert r2.json()["data"]["status"] == "revoked"


def test_revoke_other_users_key_404(client: TestClient, auth_token: str, viewer_user: User, db_session: Session):
    """注销别人的 Key → 404（归属校验在 service，user_id 过滤）。"""
    from app.services.mcp_key_service import MCPKeyService

    key_obj, plaintext = MCPKeyService(db_session).create_key(
        user_id=viewer_user.id, name="viewer-owned", validity_days=7,
    )
    resp = client.delete(
        f"/api/v1/users/me/mcp-keys/{key_obj.id}", headers=_auth(auth_token)
    )
    assert resp.json()["code"] == 404


# ---------------------------------------------------------------------------
# /users/{user_id}/mcp-keys（admin）
# ---------------------------------------------------------------------------

def test_admin_list_user_keys(client: TestClient, admin_token: str, auth_token: str, test_user: User, one_key: dict):
    resp = client.get(
        f"/api/v1/users/{test_user.id}/mcp-keys", headers=_auth(admin_token)
    )
    body = resp.json()
    assert body["code"] == 200
    assert len(body["data"]) == 1
    assert "key" not in body["data"][0]  # admin 也看不到明文

    # 非 admin → 403
    resp2 = client.get(
        f"/api/v1/users/{test_user.id}/mcp-keys", headers=_auth(auth_token)
    )
    assert resp2.json()["code"] == 403


def test_admin_proxy_create_and_revoke(client: TestClient, admin_token: str, viewer_user: User):
    """admin 给 viewer 代发（§7 admin 代发路径）→ 强制注销。"""
    resp = client.post(
        f"/api/v1/users/{viewer_user.id}/mcp-keys",
        json={"name": "viewer-by-admin", "validity_days": 30},
        headers=_auth(admin_token),
    )
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["key"].startswith("sk-mcp-")

    resp2 = client.delete(
        f"/api/v1/users/{viewer_user.id}/mcp-keys/{body['data']['id']}",
        headers=_auth(admin_token),
    )
    assert resp2.json()["code"] == 200
    assert resp2.json()["data"]["status"] == "revoked"


def test_admin_endpoints_unknown_user_404(client: TestClient, admin_token: str):
    assert client.get("/api/v1/users/99999/mcp-keys", headers=_auth(admin_token)).json()["code"] == 404
    resp = client.post(
        "/api/v1/users/99999/mcp-keys",
        json={"name": "x", "validity_days": 7},
        headers=_auth(admin_token),
    )
    assert resp.json()["code"] == 404


# ---------------------------------------------------------------------------
# 路由顺序回归：/me 不得被 /{user_id} 吞掉
# ---------------------------------------------------------------------------

def test_me_route_not_swallowed_by_user_id(client: TestClient, auth_token: str):
    """/users/me 若被 /{user_id} 先匹配会返回 422（int("me") 解析失败）——必须 200。"""
    resp = client.get("/api/v1/users/me", headers=_auth(auth_token))
    assert resp.json()["code"] == 200
