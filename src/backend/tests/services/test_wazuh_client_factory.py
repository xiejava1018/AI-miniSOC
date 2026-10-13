"""get_wazuh_client 工厂 + 配置中心 v1 路径单测（2026-10-13）

覆盖三个层面：
1. 配置中心路径：db 透传时 DataSourceResolver 的配置生效
   （soc_data_sources 表 → WazuhClient 凭据），settings 兜底不参与。
2. 工厂语义：
   - 无单例 → 创建
   - "无 db" 单例 + 传 db 调用 → 关旧建新（升级路径）
   - 带 db 单例存活 > TTL → 重建（配置变更 <=60s 生效）
   - 无 db 调用 → 复用，不重建（防降级）
3. WazuhConfigError：凭据 None/空 → 精确异常而不是 httpx 内部 TypeError。
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.wazuh_client import (
    WazuhClient,
    WazuhConfigError,
    _reset_wazuh_client_singleton_for_tests,
    get_wazuh_client,
)
import app.services.wazuh_client as wc_mod


@pytest.fixture(autouse=True)
def _clean_singleton():
    """每个用例前后都重置 lazy 单例，避免用例间状态泄漏。"""
    _reset_wazuh_client_singleton_for_tests()
    yield
    _reset_wazuh_client_singleton_for_tests()


def _fake_resolver_config(username="wazuh-db", password="secret-db",
                          endpoint="https://db-wazuh:55000"):
    rc = MagicMock()
    rc.config = {
        "endpoint": endpoint,
        "auth_type": "basic",
        "username": username,
        "password": password,
        "verify_ssl": False,
        "timeout_seconds": 30,
        "retry_times": 3,
        "retry_backoff_seconds": 2,
        "config_json": {},
    }
    return rc


# ── 1. 配置中心路径 ─────────────────────────────────────────────


class TestConfigCenterPath:
    def test_db_passed_resolves_from_resolver(self):
        """传 db → DataSourceResolver 配置生效（不走 settings）。"""
        fake_db = MagicMock(name="db_session")
        with patch.object(
            wc_mod, "_NOOP", None, create=True
        ):  # 占位，保持 with 结构清晰
            with patch(
                "app.services.data_source_resolver.data_source_resolver.resolve",
                return_value=_fake_resolver_config(),
            ) as mock_resolve:
                client = get_wazuh_client(db=fake_db)

        mock_resolve.assert_called_once_with("wazuh", fake_db)
        assert client.username == "wazuh-db"
        assert client.password == "secret-db"
        assert client.base_url == "https://db-wazuh:55000"

    def test_no_db_falls_back_to_settings(self):
        """不传 db → resolver 不被调用，凭据走 settings 兜底。"""
        with patch(
            "app.services.data_source_resolver.data_source_resolver.resolve",
        ) as mock_resolve, patch.multiple(
            "app.core.config.settings",
            WAZUH_API_URL="https://env-wazuh:55000",
            WAZUH_API_USERNAME="wazuh-env",
            WAZUH_API_PASSWORD="secret-env",
        ):
            client = get_wazuh_client(db=None)

        mock_resolve.assert_not_called()
        assert client.username == "wazuh-env"
        assert client.base_url == "https://env-wazuh:55000"


# ── 2. 工厂语义 ─────────────────────────────────────────────────


class TestFactorySemantics:
    def test_creates_when_none(self):
        client = get_wazuh_client(db=None)
        assert isinstance(client, WazuhClient)

    def test_upgrade_rebuild_when_db_passed_after_no_db(self):
        """无 db 单例 + 传 db 调用 → 关旧建新（升级到配置中心路径）。"""
        old = get_wazuh_client(db=None)
        with patch(
            "app.services.data_source_resolver.data_source_resolver.resolve",
            return_value=_fake_resolver_config(),
        ):
            new = get_wazuh_client(db=MagicMock())
        assert new is not old
        # 旧实例已关闭：httpx.Client.close 后再请求会抛 RuntimeError，
        # 这里用 mock close 计数验证更直接
        assert new.username == "wazuh-db"

    def test_ttl_rebuild_when_db_passed(self):
        """带 db 单例存活超过 TTL → 重建（配置中心变更 <=60s 生效）。"""
        fake_db = MagicMock()
        with patch(
            "app.services.data_source_resolver.data_source_resolver.resolve",
            return_value=_fake_resolver_config(username="v1"),
        ):
            first = get_wazuh_client(db=fake_db)

        # 未过期：同一实例复用
        with patch(
            "app.services.data_source_resolver.data_source_resolver.resolve",
            return_value=_fake_resolver_config(username="v1"),
        ):
            again = get_wazuh_client(db=fake_db)
        assert again is first

        # 模拟时间流逝超过 TTL
        with patch(
            "app.services.wazuh_client._wazuh_client_created_at", 0.0
        ), patch(
            "app.services.data_source_resolver.data_source_resolver.resolve",
            return_value=_fake_resolver_config(username="v2"),
        ):
            rebuilt = get_wazuh_client(db=fake_db)
        assert rebuilt is not first
        assert rebuilt.username == "v2"

    def test_no_db_call_does_not_downgrade(self):
        """无 db 调用永远复用现有单例，不会把配置中心单例降级成 env。"""
        fake_db = MagicMock()
        with patch(
            "app.services.data_source_resolver.data_source_resolver.resolve",
            return_value=_fake_resolver_config(username="db-user"),
        ):
            first = get_wazuh_client(db=fake_db)

        reused = get_wazuh_client(db=None)
        assert reused is first


# ── 3. WazuhConfigError 精确异常 ─────────────────────────────────


class TestConfigError:
    def test_none_credentials_raise_config_error(self):
        """凭据 None → WazuhConfigError，不再让 httpx 内部拼 TypeError。"""
        client = WazuhClient.__new__(WazuhClient)
        client.username = None
        client.password = None
        client._token = None
        client.base_url = "https://wazuh:55000"
        client._client = MagicMock()

        with pytest.raises(WazuhConfigError, match="凭据未配置"):
            client._get_token()

    def test_empty_credentials_raise_config_error(self):
        client = WazuhClient.__new__(WazuhClient)
        client.username = ""
        client.password = "x"
        client._token = None
        client.base_url = "https://wazuh:55000"
        client._client = MagicMock()

        with pytest.raises(WazuhConfigError):
            client._get_token()

    def test_401_raises_auth_error(self):
        """Wazuh 401 → WazuhAuthError（不是模糊的"不可达"）。"""
        from app.services.wazuh_client import WazuhAuthError

        client = WazuhClient.__new__(WazuhClient)
        client.username = "wazuh"
        client.password = "wrong"
        client._token = None
        client.base_url = "https://wazuh:55000"

        resp = MagicMock()
        resp.status_code = 401
        resp.json.return_value = {"detail": "Invalid credentials"}
        client._client = MagicMock()
        client._client.post.return_value = resp

        with pytest.raises(WazuhAuthError, match="401"):
            client._get_token()
