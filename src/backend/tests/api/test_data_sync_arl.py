"""OH-ARL.2 · data_sync 路由级端到端测试（arl_site / arl_vuln）。

CLAUDE.md 教训：「service 测过了不代表 endpoint 通」。
走完整 HTTP 路由：arl-collector → POST /api/v1/data/sync → data_sync.py
→ ArlSiteSyncHandler / ArlVulnSyncHandler → 落库 → source_health。

验证：
  1. arl_site 合法推送 → 200（envelope）+ DB 行 + source_health key 'arl:sync'
  2. arl_vuln 推送 → findings 旁路落库
  3. SYNC_HANDLERS 注册完整性（nat_mapping 回归 + arl 两类型）
"""


import pytest
from app.models.asset import Asset
from app.models.asset_source import AssetSource
from app.models.scanner_models import ScanFinding
from app.services.source_health import SourceHealth
from app.services.sync_handlers import SYNC_HANDLERS
from fastapi.testclient import TestClient

TEST_API_KEY = "sk-test-arl-sync"


@pytest.fixture(autouse=True)
def setup_collector_api_keys(monkeypatch):
    from unittest.mock import PropertyMock, patch

    from app.core import config as _cfg
    monkeypatch.setenv("COLLECTOR_API_KEYS", TEST_API_KEY)
    with patch.object(type(_cfg.settings), "collector_api_keys_list",
                      new_callable=PropertyMock, return_value=[TEST_API_KEY]):
        yield


def _payload(data_type: str, items: list[dict], source: str = "arl-next") -> dict:
    return {
        "source": source,
        "data_type": data_type,
        "items": items,
        "metadata": {"scopes": ["*all*"]},
    }


def _post(client: TestClient, payload: dict):
    return client.post(
        "/api/v1/data/sync",
        json=payload,
        headers={"X-API-Key": TEST_API_KEY},
    )


class TestRegistry:
    def test_arl_types_registered(self):
        assert "arl_site" in SYNC_HANDLERS
        assert "arl_vuln" in SYNC_HANDLERS
        assert SYNC_HANDLERS["arl_site"].data_type == "arl_site"
        assert SYNC_HANDLERS["arl_vuln"].data_type == "arl_vuln"

    def test_regression_existing_types(self):
        # nat_mapping / discovery 等既有通道不被注册表改动破坏
        for k in ("asset", "port", "discovery", "nat_mapping"):
            assert k in SYNC_HANDLERS


class TestArlSiteRoute:
    def test_end_to_end(self, client: TestClient, db_session):
        # 1) 未命中 IP → findings
        resp = _post(client, _payload("arl_site", [{
            "ip": "192.168.0.77", "port": 8080, "scheme": "http",
            "service": "http", "title": "New Service",
            "url": "http://192.168.0.77:8080", "fingers": ["SolidJS"],
            "scope_id": "s-1",
        }]))
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        data = body["data"]
        assert data["total"] == 1 and data["created"] == 1

        f = (
            db_session.query(ScanFinding)
            .filter(ScanFinding.asset_ip == "192.168.0.77")
            .one()
        )
        assert f.discovery_source == "arl-next"

        # 2) source_health key 'arl:sync' 已记录（status 为运行时推导，断言成功时间戳）
        sh = (
            db_session.query(SourceHealth)
            .filter(SourceHealth.source_key == "arl:sync")
            .one_or_none()
        )
        assert sh is not None
        assert sh.source_type == "arl-next"
        assert sh.last_success_at is not None

    def test_matched_asset_upserts_source(self, client: TestClient, db_session):
        asset = Asset(name="fnNAS", asset_ip="192.168.0.60",
                      network_segment="default")
        db_session.add(asset)
        db_session.commit()

        resp = _post(client, _payload("arl_site", [{
            "ip": "192.168.0.60", "port": 9000, "scheme": "http",
            "title": "Portainer", "url": "http://192.168.0.60:9000",
            "fingers": ["Portainer"], "scope_id": "s-1",
        }]))
        assert resp.status_code == 200
        src = (
            db_session.query(AssetSource)
            .filter(AssetSource.asset_id == asset.id,
                    AssetSource.source == "arl-next")
            .one()
        )
        assert src.source_status == "observed"

    def test_invalid_item_fails_gracefully(self, client: TestClient, db_session):
        resp = _post(client, _payload("arl_site", [{"ip": "not-an-ip", "port": 1}]))
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200  # envelope：HTTP 恒 200
        assert body["data"]["failed"] == 1


class TestArlVulnRoute:
    def test_end_to_end_findings(self, client: TestClient, db_session):
        resp = _post(client, _payload("arl_vuln", [{
            "ip": "192.168.0.42",
            "url": "https://192.168.0.42:5173",
            "plugin_name": "Swagger_Json_Identify",
            "app_name": "Swagger",
            "cve_ids": [],
            "source_table": "asset_vuln",
        }]))
        assert resp.status_code == 200
        assert resp.json()["data"]["created"] == 1
        f = (
            db_session.query(ScanFinding)
            .filter(ScanFinding.asset_ip == "192.168.0.42")
            .one()
        )
        assert f.discovery_source == "arl-next"
        assert f.raw_data["vulns"][0]["plugin_name"] == "Swagger_Json_Identify"
