# tests/models/test_sync_task.py
import pytest
from datetime import datetime, timezone
from app.models.sync_task import SyncTask

def test_create_sync_task(db_session):
    """测试创建同步任务"""
    task = SyncTask(
        sync_type="manual",
        status="pending",
        total_count=0
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    assert task.id is not None
    assert task.sync_type == "manual"
    assert task.status == "pending"
    assert task.total_count == 0
    assert task.created_at is not None

def test_sync_task_status_enum(db_session):
    """测试同步任务状态"""
    valid_statuses = ["pending", "running", "completed", "failed"]

    for status in valid_statuses:
        task = SyncTask(
            sync_type="manual",
            status=status
        )
        db_session.add(task)
        db_session.commit()

    assert db_session.query(SyncTask).count() == len(valid_statuses)
