"""
测试：GET /api/v1/roles/{id}/menus 返回结构

回归用例 —— 防止返回结构回退到扁平 + 顶层 authList 形态。
与前端 src/views/system/role/auth.vue 期望契约：
- menus 为树形（每节点含 children 数组）
- meta.{title,icon,authList,hasPermission} 嵌套在 meta 内
- hasPermission 标志正确反映授权情况
"""
import pytest
from fastapi.testclient import TestClient

from app.core.auth import create_access_token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_admin_test_setup(db_session, *, username="admin_test_only"):
    """
    在 db_session 内手工创建 code='admin' 的角色和对应用户。

    不通过 fixture（conftest 已有 admin_user 但绑定 sample_role，
    而 sample_role.code='test_role' 导致 User.is_admin 为 False）。
    """
    from app.core.security import get_password_hash
    from app.models.user import User, UserStatus
    from app.models.role import Role

    role = Role(name="管理员-test", code="admin", description="test admin")
    db_session.add(role)
    db_session.flush()

    user = User(
        username=username,
        password_hash=get_password_hash("admin123"),
        email=f"{username}@example.com",
        full_name="Admin Test",
        role_id=role.id,
        status=UserStatus.ACTIVE,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def _admin_token(user) -> str:
    return create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
            "is_admin": True,
            "is_active": True,
            "is_locked": False,
        }
    )


class TestGetRoleMenusStructure:
    """GET /api/v1/roles/{id}/menus 契约测试"""

    def test_returns_tree_structure(
        self, client: TestClient, db_session, sample_role, sample_menus
    ):
        """顶级菜单应含 children 数组（树形而非扁平）"""
        admin = _make_admin_test_setup(db_session)
        token = _admin_token(admin)
        response = client.get(f"/api/v1/roles/{sample_role.id}/menus", headers=_auth(token))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["code"] == 200

        data = body["data"]
        assert len(data["menus"]) == len(sample_menus)
        for m in data["menus"]:
            assert "children" in m, f"menu {m['id']} missing children field"
            assert isinstance(m["children"], list)

    def test_meta_contains_auth_list(
        self, client: TestClient, db_session, sample_role, sample_menus
    ):
        """菜单 meta 字段必须包含 authList 数组"""
        admin = _make_admin_test_setup(db_session, username="admin_meta_test")
        from app.models.menu import Menu
        # 按 name 定位 target（解耦 path 单复数；sample_menus 的 path 故意保留复数）
        target = db_session.query(Menu).filter(Menu.name == "用户管理").first()
        target.permissions = [
            {"title": "查看", "authMark": "view"},
            {"title": "新增", "authMark": "add"},
            {"title": "编辑", "authMark": "edit"},
        ]
        db_session.commit()

        token = _admin_token(admin)
        response = client.get(f"/api/v1/roles/{sample_role.id}/menus", headers=_auth(token))
        assert response.status_code == 200, response.text

        menus = response.json()["data"]["menus"]
        target_menu = next(m for m in menus if m["id"] == target.id)
        # 关键契约：meta 字段必须存在且包含 authList（前端依赖此字段）
        assert "meta" in target_menu, "menu must expose nested meta field"
        assert isinstance(target_menu["meta"]["authList"], list)
        assert len(target_menu["meta"]["authList"]) == 3
        for item in target_menu["meta"]["authList"]:
            assert "authMark" in item
            assert "hasPermission" in item

    def test_has_permission_reflects_grant(
        self, client: TestClient, db_session
    ):
        """未授权的按钮权限 hasPermission 应为 False"""
        admin = _make_admin_test_setup(db_session, username="admin_hp_test")
        from app.models.menu import Menu
        from app.models.role import Role
        from app.models.role_menu import RoleMenu

        m = Menu(path="x-page", name="X Page", permissions=[
            {"title": "查看", "authMark": "view"},
            {"title": "删除", "authMark": "delete"},
        ])
        db_session.add(m)
        db_session.flush()
        role = Role(name="limited", code="limited")
        db_session.add(role)
        db_session.flush()
        db_session.add(RoleMenu(role_id=role.id, menu_id=m.id, permissions=["view"]))
        db_session.commit()
        db_session.refresh(m)

        token = _admin_token(admin)
        response = client.get(f"/api/v1/roles/{role.id}/menus", headers=_auth(token))
        assert response.status_code == 200, response.text
        menus = response.json()["data"]["menus"]
        assert len(menus) == 1
        x = menus[0]
        assert x["id"] == m.id
        assert x["meta"]["hasPermission"] is True
        auth_marks = {a["authMark"]: a["hasPermission"] for a in x["meta"]["authList"]}
        assert auth_marks.get("view") is True
        assert auth_marks.get("delete") is False

    def test_empty_role_returns_no_menus(
        self, client: TestClient, db_session
    ):
        """无任何菜单授权的角色，menus 应为空数组"""
        admin = _make_admin_test_setup(db_session, username="admin_empty_test")
        from app.models.role import Role

        role = Role(name="empty", code="empty")
        db_session.add(role)
        db_session.commit()
        db_session.refresh(role)

        token = _admin_token(admin)
        response = client.get(f"/api/v1/roles/{role.id}/menus", headers=_auth(token))
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["code"] == 200
        assert body["data"]["menus"] == []
        assert body["data"]["menu_ids"] == []
        assert body["data"]["role_id"] == role.id

    def test_assign_then_get_roundtrip(
        self, client: TestClient, db_session
    ):
        """分配菜单后 GET 应能拿到一致结构"""
        admin = _make_admin_test_setup(db_session, username="admin_rt_test")
        from app.models.menu import Menu
        from app.models.role import Role
        from app.models.role_menu import RoleMenu

        m1 = Menu(path="page-a", name="Page A")
        m2 = Menu(path="page-b", name="Page B")
        db_session.add_all([m1, m2])
        db_session.flush()
        role = Role(name="rt", code="rt")
        db_session.add(role)
        db_session.flush()
        db_session.add(RoleMenu(role_id=role.id, menu_id=m1.id, permissions=[]))
        db_session.commit()

        token = _admin_token(admin)
        response = client.get(f"/api/v1/roles/{role.id}/menus", headers=_auth(token))
        assert response.status_code == 200, response.text
        data = response.json()["data"]
        assert len(data["menus"]) == 1
        assert data["menus"][0]["id"] == m1.id
        assert data["menu_ids"] == [m1.id]

    def test_requires_admin(
        self, client: TestClient, test_user, sample_role
    ):
        """非 admin 调用应通过业务码 403 拒绝（HTTP 状态恒为 200）"""
        token = create_access_token(
            data={"sub": str(test_user.id), "is_admin": False, "is_active": True, "is_locked": False}
        )
        response = client.get(f"/api/v1/roles/{sample_role.id}/menus", headers=_auth(token))
        assert response.status_code == 200  # 项目统一 HTTP 200
        body = response.json()
        assert body["code"] == 403  # 业务码表示权限不足

    def test_nonexistent_role_returns_404(
        self, client: TestClient, db_session
    ):
        """不存在的 role_id 通过业务码 404 拒绝（HTTP 恒为 200）"""
        admin = _make_admin_test_setup(db_session, username="admin_404_test")
        token = _admin_token(admin)
        response = client.get("/api/v1/roles/999999/menus", headers=_auth(token))
        assert response.status_code == 200
        body = response.json()
        assert body["code"] == 404
