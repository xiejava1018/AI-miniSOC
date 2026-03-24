# tests/models/test_asset_change_log.py
import pytest
from app.models.asset_change_log import AssetChangeLog
from app.models.asset import Asset
from app.models.sync_task import SyncTask

def test_create_asset_change_log(db_session, test_asset):
    """测试创建资产变更日志"""
    log = AssetChangeLog(
        asset_id=test_asset.id,
        change_type="status_changed",
        field_name="asset_status",
        old_value="在线",
        new_value="离线"
    )
    db_session.add(log)
    db_session.commit()
    db_session.refresh(log)

    assert log.id is not None
    assert log.asset_id == test_asset.id
    assert log.change_type == "status_changed"
    assert log.field_name == "asset_status"
    assert log.old_value == "在线"
    assert log.new_value == "离线"
    assert log.changed_at is not None

def test_change_log_with_sync_task(db_session, test_asset):
    """测试关联同步任务的变更日志"""
    task = SyncTask(sync_type="manual", status="completed")
    db_session.add(task)
    db_session.commit()

    log = AssetChangeLog(
        asset_id=test_asset.id,
        sync_task_id=task.id,
        change_type="created"
    )
    db_session.add(log)
    db_session.commit()

    assert log.sync_task_id == task.id
