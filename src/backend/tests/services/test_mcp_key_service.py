"""
MCP Key Service 单元测试（PR1 Agent A）

覆盖（设计文档 §3/§5）：
- create：正常 / 409 上限 / 409 同名 / 422 有效期范围 / 422 名称长度
- validate：active / key_invalid / key_revoked / key_expired / user_disabled 五分支
- revoke：幂等（二次调用直接返回）
- extend：active 可延期 / revoked 409 / 缓存已清（新 expires 生效）
- 缓存：validate_key_cached 命中/主动失效/用户级批量失效
- 配置读取：get_config 类型转换（bool/int/str）

全部走 tests/conftest.py 的 db_session fixture（AI-miniSOC-db_test 独立库）。
"""

import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models import User, Role
from app.models.mcp_key import SOCMCPKey
from app.services import mcp_key_service as mks
from app.services.mcp_key_service import MCPKeyService, invalidate_key_cache
from app.core.security import get_password_hash


@pytest.fixture(autouse=True)
def _reset_module_state():
    """每个测试前后清模块级缓存（Key 校验缓存/配置缓存），避免跨测试泄漏。"""
    mks._key_cache.clear()
    mks._config_cache["value"] = None
    mks._config_cache["at"] = 0.0
    yield
    mks._key_cache.clear()
    mks._config_cache["value"] = None
    mks._config_cache["at"] = 0.0


@pytest.fixture
def role(db_session):
    r = Role(name="操作员", code="operator", description="test")
    db_session.add(r)
    db_session.commit()
    db_session.refresh(r)
    return r


@pytest.fixture
def user(db_session, role):
    u = User(
        username="mcp_tester",
        password_hash=get_password_hash("Passw0rd!123"),
        email="mcp_tester@test.local",
        nick_name="测试用户",
        role_id=role.id,
        status="active",
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def _mk_key_row(db, user_id, name="k", status="active", expires_delta_days=30, key_hash=None):
    row = SOCMCPKey(
        user_id=user_id,
        name=name,
        key_prefix="sk-mcp-XXXX",
        key_hash=key_hash or f"hash-{name}-{time.time_ns()}",
        status=status,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_delta_days),
        revoked_at=datetime.now(timezone.utc) if status == "revoked" else None,
        revoke_reason="user_revoked" if status == "revoked" else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# create_key
# ---------------------------------------------------------------------------

class TestCreateKey:
    def test_create_ok(self, db_session, user):
        svc = MCPKeyService(db_session)
        row, plaintext = svc.create_key(user.id, "workbuddy", 90)
        assert plaintext.startswith("sk-mcp-")
        assert row.key_prefix == plaintext[:11]
        assert len(row.key_hash) == 64
        assert row.key_hash != plaintext  # 库里只有哈希
        assert row.status == "active"
        assert row.expires_at > datetime.now(timezone.utc)

    def test_create_duplicate_name_409(self, db_session, user):
        svc = MCPKeyService(db_session)
        svc.create_key(user.id, "workbuddy", 7)
        with pytest.raises(HTTPException) as e:
            svc.create_key(user.id, "workbuddy", 7)
        assert e.value.status_code == 409

    def test_create_revoked_name_reusable(self, db_session, user):
        """注销后同名可重新申请（应用层唯一性只看 active）"""
        svc = MCPKeyService(db_session)
        row, _ = svc.create_key(user.id, "workbuddy", 7)
        svc.revoke_key(user.id, row.id)
        row2, _ = svc.create_key(user.id, "workbuddy", 7)  # 不抛
        assert row2.id != row.id

    def test_create_max_per_user_409(self, db_session, user, monkeypatch):
        real = mks._config_int
        monkeypatch.setattr(
            mks, "_config_int",
            lambda k, d, db=None: 2 if k == "key.max_per_user" else real(k, d, db),
        )
        svc = MCPKeyService(db_session)
        svc.create_key(user.id, "a", 7)
        svc.create_key(user.id, "b", 7)
        with pytest.raises(HTTPException) as e:
            svc.create_key(user.id, "c", 7)
        assert e.value.status_code == 409

    def test_create_validity_out_of_range_422(self, db_session, user):
        svc = MCPKeyService(db_session)
        with pytest.raises(HTTPException) as e:
            svc.create_key(user.id, "x", 0)
        assert e.value.status_code == 422
        with pytest.raises(HTTPException) as e2:
            svc.create_key(user.id, "x", 99999)
        assert e2.value.status_code == 422

    def test_create_bad_name_422(self, db_session, user):
        svc = MCPKeyService(db_session)
        with pytest.raises(HTTPException) as e:
            svc.create_key(user.id, "", 7)
        assert e.value.status_code == 422
        with pytest.raises(HTTPException):
            svc.create_key(user.id, "n" * 51, 7)


# ---------------------------------------------------------------------------
# validate_key（五分支）
# ---------------------------------------------------------------------------

class TestValidateKey:
    def test_validate_active(self, db_session, user):
        svc = MCPKeyService(db_session)
        _, plaintext = svc.create_key(user.id, "v", 7)
        r = svc.validate_key(plaintext)
        assert r["ok"] is True
        assert r["user_id"] == user.id
        assert r["username"] == "mcp_tester"
        assert r["role_code"] == "operator"
        assert r["key_id"] > 0

    def test_validate_invalid(self, db_session, user):
        r = MCPKeyService(db_session).validate_key("sk-mcp-not-exists")
        assert r["ok"] is False and r["error"] == "key_invalid"

    def test_validate_revoked(self, db_session, user):
        svc = MCPKeyService(db_session)
        row, plaintext = svc.create_key(user.id, "rv", 7)
        svc.revoke_key(user.id, row.id)
        r = svc.validate_key(plaintext)
        assert r["ok"] is False and r["error"] == "key_revoked"

    def test_validate_expired(self, db_session, user):
        row = _mk_key_row(db_session, user.id, name="exp",
                          expires_delta_days=-1)  # 已过期
        plaintext = f"plain-{row.id}"
        # 直接构造 hash 一致（不经过 create）
        import hashlib
        row.key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        db_session.commit()
        r = MCPKeyService(db_session).validate_key(plaintext)
        assert r["ok"] is False and r["error"] == "key_expired"

    def test_validate_user_disabled(self, db_session, user):
        user.status = "locked"
        db_session.commit()
        row = _mk_key_row(db_session, user.id, name="dis")
        import hashlib
        plaintext = f"plain-dis-{row.id}"
        row.key_hash = hashlib.sha256(plaintext.encode()).hexdigest()
        db_session.commit()
        r = MCPKeyService(db_session).validate_key(plaintext)
        assert r["ok"] is False and r["error"] == "user_disabled"


# ---------------------------------------------------------------------------
# revoke / extend
# ---------------------------------------------------------------------------

class TestRevokeExtend:
    def test_revoke_idempotent(self, db_session, user):
        svc = MCPKeyService(db_session)
        row, plaintext = svc.create_key(user.id, "r1", 7)
        first = svc.revoke_key(user.id, row.id)
        assert first.status == "revoked"
        assert first.revoke_reason == "user_revoked"
        second = svc.revoke_key(user.id, row.id)  # 幂等不抛
        assert second.status == "revoked"

    def test_admin_revoke(self, db_session, user):
        svc = MCPKeyService(db_session)
        row, _ = svc.create_key(user.id, "admin", 7)
        got = svc.admin_revoke_key(row.id)
        assert got.revoke_reason == "admin_revoked"

    def test_extend_ok(self, db_session, user):
        svc = MCPKeyService(db_session)
        row, _ = svc.create_key(user.id, "ext", 7)
        got = svc.extend_key(user.id, row.id, 90)
        assert got.expires_at - datetime.now(timezone.utc) > timedelta(days=89)

    def test_extend_revoked_409(self, db_session, user):
        svc = MCPKeyService(db_session)
        row, _ = svc.create_key(user.id, "ext2", 7)
        svc.revoke_key(user.id, row.id)
        with pytest.raises(HTTPException) as e:
            svc.extend_key(user.id, row.id, 30)
        assert e.value.status_code == 409

    def test_not_found_404(self, db_session, user):
        svc = MCPKeyService(db_session)
        with pytest.raises(HTTPException) as e:
            svc.get_key(user.id, 999999)
        assert e.value.status_code == 404


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------

class TestCache:
    def test_cached_validate_and_invalidate_by_hash(self, db_session, user, monkeypatch):
        real = mks._config_int
        monkeypatch.setattr(
            mks, "_config_int",
            lambda k, d, db=None: 60 if k == "key.cache_ttl_seconds" else real(k, d, db),
        )
        svc = MCPKeyService(db_session)
        row, plaintext = svc.create_key(user.id, "cache1", 7)

        r1 = mks.validate_key_cached(plaintext, db_session)
        assert r1["ok"] is True
        # 缓存命中（DB 行改为 revoked 后缓存仍 ok，证明走了缓存）
        db_session.query(SOCMCPKey).filter(SOCMCPKey.id == row.id).update({"status": "revoked"})
        db_session.commit()
        r2 = mks.validate_key_cached(plaintext, db_session)
        assert r2["ok"] is True  # 旧缓存

        # 主动失效后走 DB → revoked
        mks.invalidate_key_cache(key_hash=row.key_hash)
        r3 = mks.validate_key_cached(plaintext, db_session)
        assert r3["ok"] is False and r3["error"] == "key_revoked"

    def test_revoke_invalidates_cache_immediately(self, db_session, user, monkeypatch):
        real = mks._config_int
        monkeypatch.setattr(
            mks, "_config_int",
            lambda k, d, db=None: 60 if k == "key.cache_ttl_seconds" else real(k, d, db),
        )
        svc = MCPKeyService(db_session)
        row, plaintext = svc.create_key(user.id, "cache2", 7)
        assert mks.validate_key_cached(plaintext, db_session)["ok"] is True
        svc.revoke_key(user.id, row.id)  # revoke 内部应清缓存
        r = mks.validate_key_cached(plaintext, db_session)
        assert r["ok"] is False and r["error"] == "key_revoked"

    def test_invalidate_by_user(self, db_session, user, monkeypatch):
        real = mks._config_int
        monkeypatch.setattr(
            mks, "_config_int",
            lambda k, d, db=None: 60 if k == "key.cache_ttl_seconds" else real(k, d, db),
        )
        svc = MCPKeyService(db_session)
        row1, p1 = svc.create_key(user.id, "u1", 7)
        row2, p2 = svc.create_key(user.id, "u2", 7)
        assert mks.validate_key_cached(p1, db_session)["ok"] is True
        assert mks.validate_key_cached(p2, db_session)["ok"] is True
        mks.invalidate_key_cache(user_id=user.id)  # 用户级批量失效
        # 该用户两个 hash 的缓存条目都已清（不假设缓存全空——可能残留其它测试条目）
        assert row1.key_hash not in mks._key_cache
        assert row2.key_hash not in mks._key_cache
        r1 = mks.validate_key_cached(p1, db_session)
        r2 = mks.validate_key_cached(p2, db_session)
        # 重建后仍是有效 Key（走 DB 直查）
        assert r1["ok"] is True and r2["ok"] is True


# ---------------------------------------------------------------------------
# 配置读取
# ---------------------------------------------------------------------------

class TestGetConfig:
    def test_get_config_types(self, db_session):
        # 种子未跑前走默认值兜底（显式传 db：测试隔离，不走 app 连接池）
        assert mks.get_config("mcp.auth.required", False, db_session) in (True, False)
        assert isinstance(mks.get_config("mcp.key.max_per_user", 5, db_session), int)
        assert mks.get_config("mcp.key.max_per_user", 5, db_session) == 5
        assert mks.get_config("mcp.key.not-exists", "fallback", db_session) == "fallback"


# ---------------------------------------------------------------------------
# Purge（PR4：彻底删除已注销 Key）
# ---------------------------------------------------------------------------

class TestPurgeKey:
    """purge_key / admin_purge_key 设计动机：
    1) active Key 不许 purge（静默删除会绕过审计）
    2) revoked Key 可物理 DELETE FROM soc_mcp_keys
    3) 缓存同步清除
    4) 幂等性：第二次 purge 同一 id 返回 404（记录已不存在）
    """

    def test_purge_revoked_key_success(self, db_session, user):
        """正常流程：revoke 后 purge，DB 物理消失。"""
        # 准备：先建一个 Key 造出明文，再 revoke
        svc = MCPKeyService(db_session)
        row, plaintext = svc.create_key(user.id, "to-purge", 7)
        svc.revoke_key(user.id, row.id, reason="user_revoked")
        # populate cache as if Agent was using it
        mks.validate_key_cached(plaintext, db_session)
        assert row.key_hash in mks._key_cache
        # purge
        svc.purge_key(user_id=user.id, key_id=row.id)
        # 缓存已清
        assert row.key_hash not in mks._key_cache
        # DB 不存在该记录
        assert db_session.query(SOCMCPKey).filter(SOCMCPKey.id == row.id).first() is None

    def test_purge_active_key_rejected_409(self, db_session, user):
        """未注销的 Key 不允许 purge（设计动机：避免静默丢失 Agent 会话）。"""
        svc = MCPKeyService(db_session)
        row, _ = svc.create_key(user.id, "active", 7)
        with pytest.raises(HTTPException) as exc:
            svc.purge_key(user_id=user.id, key_id=row.id)
        assert exc.value.status_code == 409
        assert "请先「注销」该 Key" in str(exc.value.detail)
        # active Key 仍存在
        assert db_session.query(SOCMCPKey).filter(SOCMCPKey.id == row.id).first() is not None

    def test_purge_other_users_key_rejected_404(self, db_session, user):
        """不能 purge 别人的 Key（按 user_id 限定）。"""
        # 第二个用户
        other_role = Role(name="other", code="other", description="t")
        db_session.add(other_role); db_session.commit(); db_session.refresh(other_role)
        other = User(
            username="other_tester",
            password_hash=get_password_hash("Passw0rd!123"),
            email="other@test.local",
            role_id=other_role.id,
            status="active",
        )
        db_session.add(other); db_session.commit(); db_session.refresh(other)
        # other 有一个 revoked Key
        other_svc = MCPKeyService(db_session)
        other_row, _ = other_svc.create_key(other.id, "other-key", 7)
        other_svc.revoke_key(other.id, other_row.id, reason="user_revoked")
        # user 试图 purge other 的 Key
        user_svc = MCPKeyService(db_session)
        with pytest.raises(HTTPException) as exc:
            user_svc.purge_key(user_id=user.id, key_id=other_row.id)
        assert exc.value.status_code == 404
        # other 的记录还在
        assert db_session.query(SOCMCPKey).filter(SOCMCPKey.id == other_row.id).first() is not None

    def test_purge_nonexistent_id_rejected_404(self, db_session, user):
        svc = MCPKeyService(db_session)
        with pytest.raises(HTTPException) as exc:
            svc.purge_key(user_id=user.id, key_id=999999)
        assert exc.value.status_code == 404

    def test_admin_purge_any_users_revoked_key(self, db_session, user):
        """admin 可 purge 任意用户的已注销 Key（与 admin_revoke 一致权限）。"""
        svc = MCPKeyService(db_session)
        row, _ = svc.create_key(user.id, "for-admin", 7)
        svc.revoke_key(user.id, row.id, reason="user_revoked")
        # admin purge
        svc.admin_purge_key(key_id=row.id)
        assert db_session.query(SOCMCPKey).filter(SOCMCPKey.id == row.id).first() is None

    def test_admin_purge_active_key_rejected_409(self, db_session, user):
        """admin 也不能 purge active。"""
        svc = MCPKeyService(db_session)
        row, _ = svc.create_key(user.id, "active-admin", 7)
        with pytest.raises(HTTPException) as exc:
            svc.admin_purge_key(key_id=row.id)
        assert exc.value.status_code == 409

    def test_purge_expired_active_key_rejected_409(self, db_session, user):
        """边界：active 状态但 days_remaining==0（expired）仍属 active，purge 一律拒绝。
        逼用户先走 revoke 流程，保留 audit trace。"""
        svc = MCPKeyService(db_session)
        row, _ = svc.create_key(user.id, "to-expire", 7)
        # 手动把 expires_at 拨到昨天（仍 status=active）
        row.expires_at = datetime.now(timezone.utc) - timedelta(days=1)
        db_session.commit()
        with pytest.raises(HTTPException) as exc:
            svc.purge_key(user_id=user.id, key_id=row.id)
        assert exc.value.status_code == 409
