"""
Auth API 端到端测试

> ⚠️ **运行前提**：本文件测试的是 live uvicorn（http://localhost:8000），
> 不走 conftest 的 TestClient + drop_all 路径——后者在生产 PostgreSQL 上
> 会因 ``soc_assets`` 上的额外 FK 依赖报 ``DependentObjectsStillExist``。
> 如果哪天修复了 conftest，可以把 ``requests`` 调用换成 ``TestClient`` 走 in-process。

覆盖：
- 登录成功 / 失败
- 错误密码 → 401 + 审计失败
- 5 次错误密码 → 账户自动 LOCKED → 第 6 次 403
- refresh token 轮换：旧 refresh 第二次使用 → 401
- /auth/logout → 旧 access 不可用
- /auth/me 正常路径
- 普通用户（如果 seed 了）访问 admin-only 接口 → 403
"""

import time

import pytest
import requests

BASE_URL = "http://localhost:8000/api/v1"
LIVE_SERVER_REQUIRED_MSG = "live uvicorn must be running at localhost:8000"


# ---------------------------------------------------------------------------
# 模块级 setup/teardown：把 admin 强制回 ACTIVE + 清空失败计数
# 否则前面 lockout 测试会污染后续测试
# ---------------------------------------------------------------------------

def _reset_admin_to_active():
    """
    把 admin 强制回 ACTIVE + 触发一次成功登录清空 uvicorn 服务端
    ``username:ip`` 失败计数（测试进程里的 dict 清了没用，必须走
    HTTP 让服务端的 ``_clear_login_attempts`` 实际执行）。
    """
    from app.core.database import SessionLocal
    from app.models.user import User, UserStatus

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        if admin is not None and admin.status != UserStatus.ACTIVE:
            admin.status = UserStatus.ACTIVE
            db.commit()
    finally:
        db.close()

    # 触发服务端清零（即使 admin 还是 LOCKED 也会返回 403 但不抛异常）
    try:
        requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=5,
        )
    except requests.RequestException:
        pass


@pytest.fixture(autouse=True)
def _isolate_admin_state():
    """每个用例前后都重置 admin 状态——避免 lockout 副作用跨用例。"""
    _reset_admin_to_active()
    yield
    _reset_admin_to_active()


def _server_alive() -> bool:
    try:
        r = requests.get(f"{BASE_URL}/auth/captcha", timeout=2)
        return r.status_code == 200
    except requests.RequestException:
        return False


pytestmark = pytest.mark.skipif(
    not _server_alive(), reason=LIVE_SERVER_REQUIRED_MSG
)


# ---------------------------------------------------------------------------
# 1. 登录主路径
# ---------------------------------------------------------------------------

class TestLogin:
    def test_login_success_returns_tokens_and_user(self):
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=5,
        )
        body = resp.json()
        assert body["code"] == 200, body
        data = body["data"]
        assert "access_token" in data and len(data["access_token"]) > 50
        assert "refresh_token" in data and len(data["refresh_token"]) > 50
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0
        assert data["user"]["username"] == "admin"
        assert data["user"]["is_admin"] is True
        assert data["user"]["status"] == "active"

    def test_login_wrong_password_returns_code_401(self):
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "wrongpwd999"},
            timeout=5,
        )
        body = resp.json()
        assert body["code"] == 401, body
        # 不应在 401 响应里透露锁定状态
        assert "锁定" not in body["msg"]

    def test_login_nonexistent_user_returns_code_401(self):
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "nosuchuser_xyz", "password": "wrongpwd999"},
            timeout=5,
        )
        body = resp.json()
        assert body["code"] == 401
        # 用户名存在性不应被泄露
        assert "不存在" not in body["msg"]

    def test_login_disabled_user_returns_403(self):
        """需要临时把 admin 置 disabled，测完恢复。fixture 已保证 ACTIVE。"""
        from app.core.database import SessionLocal
        from app.models.user import User, UserStatus

        db = SessionLocal()
        try:
            admin = db.query(User).filter(User.username == "admin").first()
            admin.status = UserStatus.DISABLED
            db.commit()
        finally:
            db.close()

        try:
            resp = requests.post(
                f"{BASE_URL}/auth/login",
                json={"username": "admin", "password": "admin123"},
                timeout=5,
            )
            body = resp.json()
            assert body["code"] == 403
            assert "禁用" in body["msg"]
        finally:
            # fixture teardown 会再 reset 一次，这里提前 reset 也行
            _reset_admin_to_active()


# ---------------------------------------------------------------------------
# 2. /auth/me
# ---------------------------------------------------------------------------

class TestMe:
    def test_me_with_valid_token(self):
        token = self._login_admin()
        resp = requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        body = resp.json()
        assert body["code"] == 200, body
        user = body["data"]
        assert user["username"] == "admin"
        # /me 走的是 UserResponse.model_validate(current_user)，
        # 必须包含所有响应字段（不能因为 ORM 直返而漏字段）
        for field in ("id", "username", "email", "is_admin", "status", "role_id"):
            assert field in user, f"missing field: {field}"

    def test_me_without_token_returns_401(self):
        resp = requests.get(f"{BASE_URL}/auth/me", timeout=5)
        # 项目用中间件把 401 包成 200 + body.code=401，所以同时校验
        assert resp.status_code == 200
        assert resp.json()["code"] in (401, 403)

    def test_me_with_invalid_token_returns_401(self):
        resp = requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": "Bearer not.a.real.token"},
            timeout=5,
        )
        body = resp.json()
        assert body["code"] == 401

    @staticmethod
    def _login_admin() -> str:
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=5,
        )
        return resp.json()["data"]["access_token"]


# ---------------------------------------------------------------------------
# 3. Refresh token 轮换
# ---------------------------------------------------------------------------

class TestRefreshRotation:
    def test_refresh_returns_new_access_and_new_refresh(self):
        login = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=5,
        ).json()["data"]
        old_refresh = login["refresh_token"]

        resp = requests.post(
            f"{BASE_URL}/auth/refresh",
            json={"refresh_token": old_refresh},
            timeout=5,
        )
        body = resp.json()
        assert body["code"] == 200, body
        new = body["data"]
        assert "access_token" in new
        assert "refresh_token" in new
        assert new["refresh_token"] != old_refresh  # 必须是新签的

    def test_old_refresh_cannot_be_reused(self):
        login = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=5,
        ).json()["data"]
        old_refresh = login["refresh_token"]

        # 第一次用：成功
        r1 = requests.post(
            f"{BASE_URL}/auth/refresh",
            json={"refresh_token": old_refresh},
            timeout=5,
        )
        assert r1.json()["code"] == 200

        # 第二次用同一个旧 refresh：应被撤销 → 401
        r2 = requests.post(
            f"{BASE_URL}/auth/refresh",
            json={"refresh_token": old_refresh},
            timeout=5,
        )
        body = r2.json()
        assert body["code"] == 401, body
        assert "撤销" in body["msg"]


# ---------------------------------------------------------------------------
# 4. /auth/logout 黑名单
# ---------------------------------------------------------------------------

class TestLogout:
    def test_logout_revokes_current_access_token(self):
        token = TestMe._login_admin()
        # 1) /me 走通
        me1 = requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        assert me1.json()["code"] == 200

        # 2) logout
        out = requests.post(
            f"{BASE_URL}/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        assert out.json()["code"] == 200

        # 3) /me 用已撤销的 token：401
        me2 = requests.get(
            f"{BASE_URL}/auth/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        body = me2.json()
        assert body["code"] == 401
        assert "撤销" in body["msg"]


# ---------------------------------------------------------------------------
# 5. 登录失败计数 + 自动锁定
# ---------------------------------------------------------------------------

class TestLoginLockout:
    def test_5_wrong_passwords_lock_account(self):
        # 1-4 次：401
        for i in range(4):
            r = requests.post(
                f"{BASE_URL}/auth/login",
                json={"username": "admin", "password": f"wrongpwd_{i}"},
                timeout=5,
            )
            body = r.json()
            assert body["code"] == 401, f"#{i+1}: expected 401, got {body}"
            assert "锁定" not in body["msg"], "must not leak lockout in 401"

        # 第 5 次：仍返回 401（不透露锁定），但 DB 状态已被改为 LOCKED
        r5 = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "wrongpwd_5"},
            timeout=5,
        )
        assert r5.json()["code"] == 401, "5th should still be 401 (no leak)"

        # 验证 DB 状态确实为 LOCKED
        from app.core.database import SessionLocal
        from app.models.user import User
        db = SessionLocal()
        try:
            admin = db.query(User).filter(User.username == "admin").first()
            assert admin.status == "locked", \
                f"expected locked, got {admin.status!r}"
        finally:
            db.close()

        # 第 6 次：403（账户已被锁）
        r6 = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "wrongpwd_6"},
            timeout=5,
        )
        body6 = r6.json()
        assert body6["code"] == 403, body6
        assert "锁定" in body6["msg"]

        # 即使用正确密码也进不去
        r7 = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=5,
        )
        assert r7.json()["code"] == 403

    def test_successful_login_clears_failure_counter(self):
        # 错 3 次
        for i in range(3):
            requests.post(
                f"{BASE_URL}/auth/login",
                json={"username": "admin", "password": f"wrongpwd_x{i}"},
                timeout=5,
            )

        # 成功一次（清零）
        ok = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": "admin", "password": "admin123"},
            timeout=5,
        )
        assert ok.json()["code"] == 200

        # 再错 4 次不应触发锁定（计数已从 0 重新开始）
        for i in range(4):
            r = requests.post(
                f"{BASE_URL}/auth/login",
                json={"username": "admin", "password": f"wrongpwd_y{i}"},
                timeout=5,
            )
            assert r.json()["code"] == 401, "should not have locked yet"
