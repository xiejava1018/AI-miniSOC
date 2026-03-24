"""
端到端同步测试
"""
import pytest
from sqlalchemy.orm import Session
from app.services.asset_sync import AssetSyncService
from app.models.sync_task import SyncTask
from app.models.asset import Asset
from unittest.mock import Mock, patch


@pytest.fixture
def mock_wazuh_agents():
    """Mock Wazuh agents数据"""
    return [
        {
            "id": "001",
            "name": "server-01",
            "ip": "192.168.1.10",
            "status": "active"
        },
        {
            "id": "002",
            "name": "server-02",
            "ip": "192.168.1.11",
            "status": "disconnected"
        }
    ]


@pytest.fixture
def mock_wazuh_agent_info():
    """Mock Wazuh agent详情"""
    return {
        "id": "001",
        "name": "server-01",
        "ip": "192.168.1.10",
        "status": "active",
        "os": {
            "name": "Ubuntu",
            "version": "22.04"
        },
        "cpu": {
            "cores": 4,
            "name": "Intel Core i7"
        },
        "memory": {
            "total": 8589934592
        }
    }


@patch('app.services.asset_sync.wazuh_client.get_agents')
def test_manual_sync_e2e(mock_get_agents, db_session, mock_wazuh_agents):
    """测试手动同步端到端流程"""
    # Mock Wazuh API响应
    mock_get_agents.return_value = {"data": {"affected_items": mock_wazuh_agents}}

    # 创建同步服务
    service = AssetSyncService(db_session)

    # 执行同步
    task = service.sync_from_wazuh_with_tracking("manual")

    # 验证任务
    assert task.sync_type == "manual"
    assert task.status == "completed"
    assert task.total_count == 2
    assert task.started_at is not None
    assert task.completed_at is not None

    # 验证资产已创建/更新
    assets = db_session.query(Asset).filter(
        Asset.data_source == "wazuh"
    ).all()
    assert len(assets) == 2

    # 验证资产详情
    asset1 = db_session.query(Asset).filter(Asset.wazuh_agent_id == "001").first()
    assert asset1 is not None
    assert asset1.asset_ip == "192.168.1.10"
    assert asset1.data_source == "wazuh"

    asset2 = db_session.query(Asset).filter(Asset.wazuh_agent_id == "002").first()
    assert asset2 is not None
    assert asset2.asset_status == "离线"  # status should be mapped


@patch('app.services.asset_sync.wazuh_client.get_agent_info')
@patch('app.services.asset_sync.wazuh_client.get_agents')
def test_webhook_sync_e2e(mock_get_agent_info, mock_get_agents, db_session, client, mock_wazuh_agent_info):
    """测试Webhook同步端到端流程"""
    # Mock Wazuh API响应
    mock_get_agent_info.return_value = mock_wazuh_agent_info

    # 模拟webhook请求
    response = client.post(
        "/api/v1/webhooks/wazuh",
        json={
            "agent_id": "001",
            "agent_name": "server-01",
            "rule_id": "504"
        },
        headers={"X-API-Key": "test-webhook-key"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["asset_id"] is not None

    # 验证资产已创建
    asset = db_session.query(Asset).filter(
        Asset.wazuh_agent_id == "001"
    ).first()
    assert asset is not None
    assert asset.data_source == "wazuh"
    assert asset.last_synced_at is not None


@patch('app.services.asset_sync.wazuh_client.get_agent_info')
def test_sync_creates_change_log(mock_get_agent_info, db_session):
    """测试同步创建变更日志"""
    # Mock agent info
    mock_get_agent_info.return_value = {
        "id": "003",
        "name": "server-03",
        "ip": "192.168.1.12",
        "status": "disconnected"
    }

    service = AssetSyncService(db_session)
    asset = service.sync_single_agent_webhook("003")

    # 验证变更日志
    from app.models.asset_change_log import AssetChangeLog
    change_log = db_session.query(AssetChangeLog).filter(
        AssetChangeLog.asset_id == asset.id
    ).first()
    assert change_log is not None
    assert change_log.change_type == "created"


@patch('app.services.asset_sync.wazuh_client.get_agent_info')
def test_sync_status_change_creates_log(mock_get_agent_info, db_session):
    """测试状态变更创建日志"""
    # 第一次创建
    mock_get_agent_info.return_value = {
        "id": "004",
        "name": "server-04",
        "ip": "192.168.1.13",
        "status": "active"
    }

    service = AssetSyncService(db_session)
    asset = service.sync_single_agent_webhook("004")

    # 第二次同步（状态改变）
    mock_get_agent_info.return_value = {
        "id": "004",
        "name": "server-04",
        "ip": "192.168.1.13",
        "status": "disconnected"
    }

    asset2 = service.sync_single_agent_webhook("004")

    # 验证状态变更日志
    from app.models.asset_change_log import AssetChangeLog
    status_changes = db_session.query(AssetChangeLog).filter(
        AssetChangeLog.asset_id == asset.id,
        AssetChangeLog.change_type == "status_changed"
    ).all()
    assert len(status_changes) == 1
    assert status_changes[0].old_value == "在线"  # active mapped to 在线
    assert status_changes[0].new_value == "离线"  # disconnected mapped to 离线
