"""
测试资产同步服务
"""
import pytest
from unittest.mock import Mock, patch
from app.services.asset_sync import AssetSyncService
from app.models.sync_task import SyncTask
from app.models.asset_change_log import AssetChangeLog
from app.models.asset import Asset


@pytest.fixture
def mock_wazuh_client():
    """Mock Wazuh客户端"""
    with patch('app.services.asset_sync.wazuh_client') as mock:
        yield mock


@pytest.fixture
def sample_agents():
    """示例Wazuh agents"""
    return [
        {
            "id": "001",
            "name": "web-server-01",
            "ip": "192.168.1.10",
            "status": "active"
        },
        {
            "id": "002",
            "name": "db-server-01",
            "ip": "192.168.1.20",
            "status": "disconnected"
        }
    ]


def test_sync_with_tracking_success(db_session, mock_wazuh_client, sample_agents):
    """测试带追踪的同步 - 成功场景"""
    # Mock wazuh_client返回
    mock_wazuh_client.get_agents.return_value = sample_agents

    service = AssetSyncService(db_session)
    task = service.sync_from_wazuh_with_tracking("manual")

    # 验证任务记录
    assert task.sync_type == "manual"
    assert task.status == "completed"
    assert task.started_at is not None
    assert task.completed_at is not None
    assert task.total_count == 2
    assert task.created_count == 2  # 新创建
    assert task.updated_count == 0
    assert task.failed_count == 0


def test_sync_with_tracking_failure(db_session, mock_wazuh_client):
    """测试带追踪的同步 - 失败场景"""
    # Mock wazuh_client抛出异常
    mock_wazuh_client.get_agents.side_effect = Exception("Wazuh API错误")

    service = AssetSyncService(db_session)

    with pytest.raises(Exception, match="Wazuh API错误"):
        service.sync_from_wazuh_with_tracking("manual")

    # 验证任务记录为失败状态
    tasks = db_session.query(SyncTask).all()
    assert len(tasks) == 1
    task = tasks[0]
    assert task.sync_type == "manual"
    assert task.status == "failed"
    assert task.started_at is not None
    assert task.completed_at is not None
    assert task.error_message == "Wazuh API错误"


def test_webhook_sync_new_agent(db_session, mock_wazuh_client):
    """测试Webhook同步新agent"""
    agent_data = {
        "id": "003",
        "name": "new-server",
        "ip": "192.168.1.30",
        "status": "active"
    }
    mock_wazuh_client.get_agent_info.return_value = agent_data

    service = AssetSyncService(db_session)
    asset = service.sync_single_agent_webhook("003")

    # 验证资产创建
    assert asset is not None
    assert asset.wazuh_agent_id == "003"
    assert asset.data_source == "wazuh"
    assert asset.last_synced_at is not None
    assert asset.name == "new-server"
    assert asset.asset_ip == "192.168.1.30"
    assert asset.asset_status == "在线"

    # 检查是否创建了变更日志
    change_log = db_session.query(AssetChangeLog).filter(
        AssetChangeLog.asset_id == asset.id
    ).first()
    assert change_log is not None
    assert change_log.change_type == "created"


def test_webhook_sync_existing_agent_status_change(db_session, mock_wazuh_client, test_asset):
    """测试Webhook同步现有agent - 状态变更"""
    # 先创建一个已存在的资产
    test_asset.wazuh_agent_id = "004"
    test_asset.asset_status = "在线"
    test_asset.data_source = "wazuh"
    db_session.commit()

    # Mock agent数据返回不同的状态
    agent_data = {
        "id": "004",
        "name": test_asset.name,
        "ip": test_asset.asset_ip,
        "status": "disconnected"  # 状态改变
    }
    mock_wazuh_client.get_agent_info.return_value = agent_data

    service = AssetSyncService(db_session)
    asset = service.sync_single_agent_webhook("004")

    # 验证资产更新
    assert asset.id == test_asset.id
    assert asset.asset_status == "离线"  # 状态已更新
    assert asset.last_synced_at is not None

    # 检查是否创建了状态变更日志
    change_logs = db_session.query(AssetChangeLog).filter(
        AssetChangeLog.asset_id == asset.id
    ).all()
    assert len(change_logs) == 1
    assert change_logs[0].change_type == "status_changed"
    assert change_logs[0].field_name == "asset_status"
    assert change_logs[0].old_value == "在线"
    assert change_logs[0].new_value == "离线"


def test_webhook_sync_existing_agent_no_status_change(db_session, mock_wazuh_client, test_asset):
    """测试Webhook同步现有agent - 状态未变更"""
    # 先创建一个已存在的资产
    test_asset.wazuh_agent_id = "005"
    test_asset.asset_status = "在线"
    test_asset.data_source = "wazuh"
    db_session.commit()

    # Mock agent数据返回相同的状态
    agent_data = {
        "id": "005",
        "name": test_asset.name,
        "ip": test_asset.asset_ip,
        "status": "active"  # 状态相同
    }
    mock_wazuh_client.get_agent_info.return_value = agent_data

    service = AssetSyncService(db_session)
    asset = service.sync_single_agent_webhook("005")

    # 验证资产更新（但没有状态变更日志）
    assert asset.id == test_asset.id
    assert asset.asset_status == "在线"

    # 检查没有创建状态变更日志
    change_logs = db_session.query(AssetChangeLog).filter(
        AssetChangeLog.asset_id == asset.id,
        AssetChangeLog.change_type == "status_changed"
    ).all()
    assert len(change_logs) == 0
