"""
PortSyncHandler HTTP 端到端测试（P3/F-S2）

CLAUDE.md 教训（:661, :1386）：「service 测过了不代表 endpoint 通」。
本测试通过 fastapi TestClient 走完整 HTTP 路由：
  scanner → POST /api/v1/data/sync → data_sync.py → PortSyncHandler.handle()
  → AssetPort 落库 → source_health 记录 → sync_task 状态机

验证：
  1. 合法 item 推 → 200 + DB 行写入
  2. 非法 item → 200 但 failed 计入 + 死信 (HTTP 包装层总返 200，业务码在 body)
  3. 数据通道健康键 scanner:ports 自动注册
  4. asset_id 反查
"""

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_port import AssetPort


# 测试用 API key（固定值；conftest 的 db_session 之前 fixture 链不会污染）
TEST_API_KEY = "sk-test-port-sync-handler"


@pytest.fixture(autouse=True)
def setup_collector_api_keys(monkeypatch):
    """让 collector_api_keys_list 返回 ['sk-test-port-sync-handler']。

    实现：override Settings 实例的 collector_api_keys_list property（用 patch.object + PropertyMock）。
    免调 reload，避免连锁副作用。
    """
    from unittest.mock import PropertyMock, patch
    from app.core import config as _cfg
    monkeypatch.setenv("COLLECTOR_API_KEYS", TEST_API_KEY)
    with patch.object(type(_cfg.settings), "collector_api_keys_list",
                     new_callable=PropertyMock, return_value=[TEST_API_KEY]):
        yield


def _make_payload(items, source="scanner-port"):
    """构造 /data/sync 完整 payload。"""
    return {
        "source": source,
        "data_type": "port",
        "items": items,
    }


def _port_item(**overrides):
    item = {
        "asset_ip": "203.0.113.10",
        "port": 22,
        "protocol": "tcp",
        "state": "open",
        "service": "ssh",
        "version": "OpenSSH 8.4p1",
        "service_banner": "SSH-2.0-OpenSSH_8.4p1",
        "scan_time": "2026-08-26T03:00:00Z",
    }
    item.update(overrides)
    return item


# =============================================================================
# 1. 端到端 happy path：合法 item → 200 + DB 写入
# =============================================================================
def test_endpoint_e2e_happy_path(client: TestClient, db_session: Session):
    payload = _make_payload([_port_item(asset_ip="203.0.113.10", port=22)])
    headers = {"X-API-Key": TEST_API_KEY}

    resp = client.post("/api/v1/data/sync", json=payload, headers=headers)

    assert resp.status_code == 200
    body = resp.json()
    # 响应包装中间件：{code, msg, data}
    assert body["code"] == 200
    data = body["data"]
    assert data["data_type"] == "port"
    assert data["source"] == "scanner-port"
    assert data["total"] == 1
    assert data["created"] == 1
    assert data["failed"] == 0
    # dead_letter_batch_id 可能为 null（success-only 场景），但 key 必须存在
    assert data.get("dead_letter_batch_id") is not None   # items 非空一定有 batch_id

    # 验证 DB 行写入
    db_session.commit()  # 让 handler 的 commit 生效
    port = db_session.query(AssetPort).filter(
        AssetPort.asset_ip == "203.0.113.10",
        AssetPort.port == 22,
    ).one()
    assert port.service == "ssh"
    assert port.version == "OpenSSH 8.4p1"


# =============================================================================
# 2. API Key 鉴权：缺 X-API-Key → 401
# =============================================================================
def test_endpoint_requires_api_key(client: TestClient):
    payload = _make_payload([_port_item()])
    resp = client.post("/api/v1/data/sync", json=payload)  # 无 header
    # CLAUDE.md 注意事项 #11 envelope：HTTP 恒 200，业务码在 body.code
    # X-API-Key 缺失 → FastAPI Header 必填 → 422 → envelope 包为 200+422
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] in (401, 422)   # 422 FastAPI Header 必填错；401 是显式 HTTPException
    assert "msg" in body


# =============================================================================
# 3. 不支持的 data_type → 400
# =============================================================================
def test_endpoint_unsupported_data_type(client: TestClient):
    payload = _make_payload([_port_item()])
    payload["data_type"] = "vulnerability"   # Phase 2/3 才支持
    headers = {"X-API-Key": TEST_API_KEY}
    resp = client.post("/api/v1/data/sync", json=payload, headers=headers)
    # envelope: HTTP 恒 200，业务码在 body.code
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 400
    # envelope 把 detail 改成 msg（看 response_wrapper.py:51）
    assert "不支持的数据类型" in body["msg"]
    assert "port" in body["msg"]   # 应列出支持类型


# =============================================================================
# 4. 混合 item：created + failed 都能正确计数 + 死信
# =============================================================================
def test_endpoint_mixed_items_with_dead_letter(client: TestClient, db_session: Session):
    payload = _make_payload([
        _port_item(asset_ip="203.0.113.10", port=22),     # created
        _port_item(asset_ip="203.0.113.10", port=80),     # created
        {"asset_ip": "1.2.3.4", "port": None, "protocol": "tcp"},  # failed（port 缺失）
        _port_item(asset_ip="203.0.113.10", port=99999),   # failed（端口越界）
    ])
    headers = {"X-API-Key": TEST_API_KEY}

    resp = client.post("/api/v1/data/sync", json=payload, headers=headers)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["total"] == 4
    assert data["created"] == 2
    assert data["failed"] == 2

    db_session.commit()
    rows = db_session.query(AssetPort).filter(
        AssetPort.asset_ip == "203.0.113.10",
    ).all()
    assert len(rows) == 2

    # 死信应有 2 条
    from app.models.sync_dead_letter import SyncDeadLetter
    dead_letters = db_session.query(SyncDeadLetter).filter(
        SyncDeadLetter.data_type == "port",
    ).all()
    assert len(dead_letters) >= 2


# =============================================================================
# 5. asset_id 反查：IP 命中 soc_assets → 自动挂上
# =============================================================================
def test_endpoint_attaches_asset_id_when_ip_matches(client: TestClient, db_session: Session):
    # 先在台账建一条 IP=203.0.113.10 的资产
    asset = Asset(
        network_segment="public",
        network_zone="dmz",
        asset_ip="203.0.113.10",
        name="public-server-01",
        asset_status="online",
        asset_type="server",
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    # scanner 推端口
    payload = _make_payload([_port_item(asset_ip="203.0.113.10", port=443)])
    headers = {"X-API-Key": TEST_API_KEY}
    resp = client.post("/api/v1/data/sync", json=payload, headers=headers)
    assert resp.status_code == 200
    assert resp.json()["data"]["created"] == 1

    db_session.commit()
    port = db_session.query(AssetPort).filter(
        AssetPort.asset_ip == "203.0.113.10", AssetPort.port == 443,
    ).one()
    assert port.asset_id == asset.id


# =============================================================================
# 6. source_health 自动上报：scanner:ports 成功记录
# =============================================================================
def test_endpoint_records_source_health(client: TestClient, db_session: Session):
    payload = _make_payload([_port_item()])
    headers = {"X-API-Key": TEST_API_KEY}
    resp = client.post("/api/v1/data/sync", json=payload, headers=headers)
    assert resp.status_code == 200

    db_session.commit()
    from app.models.source_health import SourceHealth
    health = db_session.query(SourceHealth).filter(
        SourceHealth.source_key == "scanner:ports"
    ).first()
    assert health is not None
    assert health.success_count >= 1
    assert health.last_success_at is not None


# =============================================================================
# 7. 重复推同一端口：第二次走 updated 路径（HTTP 层）
# =============================================================================
def test_endpoint_repeated_push_updates_existing(client: TestClient, db_session: Session):
    headers = {"X-API-Key": TEST_API_KEY}

    # 第一次
    payload = _make_payload([_port_item(
        asset_ip="203.0.113.10", port=22, version="OpenSSH 8.4p1",
    )])
    resp = client.post("/api/v1/data/sync", json=payload, headers=headers)
    assert resp.json()["data"]["created"] == 1
    db_session.commit()

    # 第二次（更精细的版本）
    payload = _make_payload([_port_item(
        asset_ip="203.0.113.10", port=22, version="OpenSSH 8.4p1 Debian 5+deb11u1",
    )])
    resp = client.post("/api/v1/data/sync", json=payload, headers=headers)
    data = resp.json()["data"]
    assert data["updated"] == 1
    assert data["created"] == 0
    db_session.commit()

    port = db_session.query(AssetPort).filter(
        AssetPort.asset_ip == "203.0.113.10", AssetPort.port == 22,
    ).one()
    assert "Debian 5+deb11u1" in port.version