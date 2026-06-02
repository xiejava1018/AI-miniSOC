"""
Token 黑名单单元测试

覆盖：
- revoke / is_revoked 基本语义
- 空 jti 不报错
- 过期 jti 自动清理（purge_expired）
- revoke 重复调用幂等
"""

import time

import pytest

from app.core import token_blacklist
from app.core.token_blacklist import revoke, is_revoked, purge_expired


@pytest.fixture(autouse=True)
def _reset_blacklist():
    """每个测试前后清空黑名单，避免污染。"""
    token_blacklist._blacklist.clear()
    yield
    token_blacklist._blacklist.clear()


class TestRevokeAndCheck:
    def test_revoke_then_is_revoked(self):
        revoke("jti-1", time.time() + 100)
        assert is_revoked("jti-1") is True

    def test_unrevoked_jti_returns_false(self):
        assert is_revoked("never-revoked") is False

    def test_empty_jti_returns_false(self):
        # 不抛异常
        assert is_revoked("") is False
        assert is_revoked(None) is False

    def test_idempotent_revoke(self):
        # 同一 jti 重复 revoke 不报错
        revoke("jti-dup", time.time() + 100)
        revoke("jti-dup", time.time() + 100)
        assert is_revoked("jti-dup") is True


class TestPurgeExpired:
    def test_purge_removes_only_expired(self):
        token_blacklist._blacklist["jti-fresh"] = time.time() + 3600
        token_blacklist._blacklist["jti-stale"] = time.time() - 3600
        purge_expired()
        assert "jti-fresh" in token_blacklist._blacklist
        assert "jti-stale" not in token_blacklist._blacklist

    def test_is_revoked_triggers_purge_of_expired(self):
        # 过期的 jti 走 is_revoked 时也应被自动清理
        token_blacklist._blacklist["jti-just-expired"] = time.time() - 1
        assert is_revoked("jti-just-expired") is False
        assert "jti-just-expired" not in token_blacklist._blacklist

    def test_revoke_clears_previous_expired(self):
        # 注入一个过期 jti，再 revoke 一次新 jti，purge_expired 应被自动调用
        token_blacklist._blacklist["jti-stale"] = time.time() - 3600
        revoke("jti-new", time.time() + 100)
        assert "jti-stale" not in token_blacklist._blacklist
        assert is_revoked("jti-new") is True


class TestRevokedSemantics:
    """与 ``core/auth.py::verify_token`` 集成的语义校验。"""

    def test_revoked_payload_causes_verify_to_raise(self):
        """通过 verify_token 间接验证：黑名单 jti 应被识别为 401 令牌已撤销。"""
        from fastapi import HTTPException

        from app.core.auth import create_access_token, verify_token

        token = create_access_token(data={"sub": "1"})
        payload = verify_token(token, "access")  # 第一次通过
        jti = payload["jti"]

        # 加入黑名单
        revoke(jti, time.time() + 3600)

        with pytest.raises(HTTPException) as exc_info:
            verify_token(token, "access")
        assert exc_info.value.status_code == 401
        assert "撤销" in exc_info.value.detail
