"""
MCP Key 认证中间件单元测试（Agent C · PR1）

覆盖（契约：docs/design/mcp-key-pr1-contract.md「Agent C 产出」节）：
- 无 Authorization 头：required=false 放行（现状兼容）
- 无 Authorization 头：required=true → 401 key_invalid
- 非法 Bearer（非 sk-mcp- 前缀 / 非 Bearer scheme）→ 401 key_invalid
- 有效 Key → 放行 + inject_identity 被调（user_id/username/JWT）+ touch_last_used 后台执行
- revoked / expired / user_disabled → 401 对应 error code
- 按 IP 连续失败 → 超阈值锁定 429；锁定期间有效 Key 也 429
- TokenManager：注入优先级 > 会话凭证；过期注入自动回落；clear_identity 回落

测试通过 monkeypatch app.services.mcp_key_service（STUB）的三个函数完成，
不起真实端口、不碰 DB。
"""

import time

import pytest
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.mcp import key_auth
from app.mcp.key_auth import MCPKeyAuthMiddleware, reset_failures
from app.mcp.token_manager import TokenManager, TokenBundle
from app.services import mcp_key_service as key_svc_stub


@pytest.fixture(autouse=True)
def _reset_state():
    """每个用例前后清空失败计数 + TokenManager 单例注入身份"""
    reset_failures()
    tm = TokenManager.get_instance()
    tm.clear_identity()
    yield
    reset_failures()
    tm.clear_identity()


def _make_app() -> Starlette:
    async def ok(_request):
        return JSONResponse({"ok": True})

    return Starlette(
        routes=[Route("/", ok, methods=["GET"])],
        middleware=[Middleware(MCPKeyAuthMiddleware)],
    )


def _patch_svc(
    monkeypatch,
    *,
    required=False,
    threshold=10,
    lock_minutes=15,
    validate=None,
    touch_calls=None,
):
    """patch stub 三个函数；返回 validate 调用记录"""
    validate_calls: list[str] = []

    def fake_get_config(key, default=None):
        cfg = {
            "mcp.auth.required": required,
            "mcp.key.failure_lock_threshold": threshold,
            "mcp.key.failure_lock_minutes": lock_minutes,
        }
        return cfg.get(key, default)

    def fake_validate(plaintext: str) -> dict:
        validate_calls.append(plaintext)
        if validate is not None:
            return validate(plaintext)
        return {"ok": False, "error": "key_invalid", "user_id": None,
                "username": None, "role_code": None, "key_id": None}

    def fake_touch(key_id: int) -> None:
        if touch_calls is not None:
            touch_calls.append(key_id)

    monkeypatch.setattr(key_svc_stub, "get_config", fake_get_config)
    monkeypatch.setattr(key_svc_stub, "validate_key_cached", fake_validate)
    monkeypatch.setattr(key_svc_stub, "touch_last_used", fake_touch)
    return validate_calls


_VALID_KEY = "sk-mcp-unit-test-valid-key"

def _valid_result(**over):
    r = {"ok": True, "error": None, "user_id": 7, "username": "alice",
         "role_code": "operator", "key_id": 42}
    r.update(over)
    return r


# ===========================================================================
# 中间件分支
# ===========================================================================

class TestNoAuthHeader:
    def test_passes_when_not_required(self, monkeypatch):
        _patch_svc(monkeypatch, required=False)
        client = TestClient(_make_app())
        r = client.get("/")
        assert r.status_code == 200
        assert r.json() == {"ok": True}

    def test_401_when_required(self, monkeypatch):
        _patch_svc(monkeypatch, required=True)
        client = TestClient(_make_app())
        r = client.get("/")
        assert r.status_code == 401
        assert r.json()["error"] == "key_invalid"
        assert r.headers.get("www-authenticate") == "Bearer"

    def test_required_true_401_does_not_count_failure(self, monkeypatch):
        # 无头 401 是配置拒绝，不是 Key 校验失败 → 不应进入失败计数
        _patch_svc(monkeypatch, required=True, threshold=2)
        client = TestClient(_make_app())
        for _ in range(3):
            assert client.get("/").status_code == 401  # 无头 × 3，不计数
        # 若无头 401 被计入，threshold=2 早已锁定，第一个带头请求应 429；
        # 实际应：失败①401 → 失败②才达阈值锁定 429，证明计数器未被无头请求污染
        _patch_svc(monkeypatch, required=False, threshold=2,
                   validate=lambda t: {"ok": False, "error": "key_invalid"})
        h = {"Authorization": "Bearer sk-mcp-x"}
        assert client.get("/", headers=h).status_code == 401
        assert client.get("/", headers=h).status_code == 429


class TestBearerParsing:
    def test_non_bearer_scheme_401(self, monkeypatch):
        calls = _patch_svc(monkeypatch)
        client = TestClient(_make_app())
        r = client.get("/", headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert r.status_code == 401
        assert r.json()["error"] == "key_invalid"
        assert calls == []  # scheme 不对，不进 Key 校验

    def test_wrong_prefix_401(self, monkeypatch):
        calls = _patch_svc(monkeypatch)
        client = TestClient(_make_app())
        r = client.get("/", headers={"Authorization": "Bearer not-a-mcp-key"})
        assert r.status_code == 401
        assert r.json()["error"] == "key_invalid"
        assert calls == []  # 前缀不对，不进 Key 校验


class TestValidKey:
    def test_pass_and_inject_identity(self, monkeypatch):
        touch: list[int] = []
        _patch_svc(
            monkeypatch,
            validate=lambda t: _valid_result() if t == _VALID_KEY
            else {"ok": False, "error": "key_invalid"},
            touch_calls=touch,
        )
        tm = TokenManager.get_instance()
        injected: list[tuple] = []
        orig_inject = tm.inject_identity
        monkeypatch.setattr(
            tm, "inject_identity",
            lambda uid, uname, token, ttl=None: injected.append((uid, uname, token))
            or orig_inject(uid, uname, token, ttl),
        )
        client = TestClient(_make_app())
        r = client.get("/", headers={"Authorization": f"Bearer {_VALID_KEY}"})
        assert r.status_code == 200
        assert r.json() == {"ok": True}

        # inject_identity 参数正确，token 是 JWT（三段式）
        assert len(injected) == 1
        uid, uname, token = injected[0]
        assert (uid, uname) == (7, "alice")
        assert isinstance(token, str) and token.count(".") == 2

        # 注入已落到单例，get_token 直接可用
        assert tm.get_token() == token

        # touch_last_used 后台执行（等最多 2s）
        for _ in range(40):
            if touch:
                break
            time.sleep(0.05)
        assert touch == [42]

    def test_jwt_payload_has_sub_username_via(self, monkeypatch):
        from app.core.auth import verify_token
        _patch_svc(monkeypatch, validate=lambda t: _valid_result())
        client = TestClient(_make_app())
        r = client.get("/", headers={"Authorization": f"Bearer {_VALID_KEY}"})
        assert r.status_code == 200
        payload = verify_token(TokenManager.get_instance().get_token(), "access")
        assert payload["sub"] == "7"
        assert payload["username"] == "alice"
        assert payload["via"] == "mcp_key"
        assert payload.get("jti")  # create_access_token 自动带 jti


class TestInvalidKey:
    @pytest.mark.parametrize("error", ["key_revoked", "key_expired", "user_disabled"])
    def test_rejected_with_error_code(self, monkeypatch, error):
        _patch_svc(monkeypatch, validate=lambda t: {
            "ok": False, "error": error, "user_id": None,
            "username": None, "role_code": None, "key_id": None})
        client = TestClient(_make_app())
        r = client.get("/", headers={"Authorization": f"Bearer {_VALID_KEY}"})
        assert r.status_code == 401
        assert r.json()["error"] == error

    def test_ok_missing_fields_treated_invalid(self, monkeypatch):
        # result 缺 ok 字段 → 按 key_invalid 处理（防御）
        _patch_svc(monkeypatch, validate=lambda t: {"user_id": 1})
        client = TestClient(_make_app())
        r = client.get("/", headers={"Authorization": f"Bearer {_VALID_KEY}"})
        assert r.status_code == 401
        assert r.json()["error"] == "key_invalid"


class TestIPLockout:
    def test_consecutive_failures_then_429(self, monkeypatch):
        _patch_svc(monkeypatch, threshold=2, lock_minutes=15,
                   validate=lambda t: {"ok": False, "error": "key_invalid"})
        client = TestClient(_make_app())
        h = {"Authorization": f"Bearer {_VALID_KEY}"}
        assert client.get("/", headers=h).status_code == 401  # 第 1 次失败
        assert client.get("/", headers=h).status_code == 429  # 达阈值 → 锁定
        # 锁定期间连有效 Key 也 429
        _patch_svc(monkeypatch, threshold=2,
                   validate=lambda t: _valid_result())
        r = client.get("/", headers=h)
        assert r.status_code == 429
        assert r.json()["error"] == "locked"

    def test_success_clears_failures(self, monkeypatch):
        state = {"fail": True}
        def validate(t):
            if state["fail"]:
                return {"ok": False, "error": "key_invalid"}
            return _valid_result()
        _patch_svc(monkeypatch, threshold=3, validate=validate)
        client = TestClient(_make_app())
        h = {"Authorization": f"Bearer {_VALID_KEY}"}
        assert client.get("/", headers=h).status_code == 401
        state["fail"] = False
        assert client.get("/", headers=h).status_code == 200  # 成功清计数
        state["fail"] = True
        assert client.get("/", headers=h).status_code == 401  # 重新计数
        assert client.get("/", headers=h).status_code == 401
        assert client.get("/", headers=h).status_code == 429  # 需再满 3 次


class TestNonHttpScope:
    def test_lifespan_scope_passes_through(self, monkeypatch):
        # lifespan / websocket scope 直接放行不报错
        _patch_svc(monkeypatch, required=True)
        mw = MCPKeyAuthMiddleware(app=lambda *a: None)
        # 构造非 http scope
        import asyncio
        scope = {"type": "lifespan"}
        seen = {}
        async def app(scope, receive, send):
            seen["called"] = True
        mw2 = MCPKeyAuthMiddleware(app=app)
        async def run():
            await mw2(scope, None, None)
        asyncio.run(run())
        assert seen.get("called") is True


# ===========================================================================
# TokenManager 注入语义
# ===========================================================================

class TestTokenManagerInjection:
    def test_inject_priority_over_bundle(self):
        tm = TokenManager()
        assert tm.get_token.__doc__  # sanity
        tm._bundle = TokenBundle(
            access_token="bundle-tok", refresh_token="r",
            expires_at=time.time() + 3600,
            refresh_expires_at=time.time() + 86400,
            username="session-user",
        )
        tm.inject_identity(1, "key-user", "injected-tok")
        assert tm.get_token() == "injected-tok"  # 注入优先
        tm.clear_identity()
        assert tm.get_token() == "bundle-tok"    # 清除后回落

    def test_inject_without_bundle(self):
        tm = TokenManager()
        tm.inject_identity(1, "key-user", "injected-tok")
        assert tm.get_token() == "injected-tok"

    def test_expired_inject_falls_back(self):
        tm = TokenManager()
        tm._bundle = TokenBundle(
            access_token="bundle-tok", refresh_token="r",
            expires_at=time.time() + 3600,
            refresh_expires_at=time.time() + 86400,
            username="session-user",
        )
        tm.inject_identity(2, "old", "expired-tok", ttl_seconds=-10)
        assert tm.get_token() == "bundle-tok"

    def test_status_reports_injection(self):
        tm = TokenManager()
        tm.inject_identity(3, "carol", "tok")
        st = tm.status()
        assert st["identity_injected"] is True
        assert st["injected_username"] == "carol"
        tm.clear_identity()
        st = tm.status()
        assert st["identity_injected"] is False
