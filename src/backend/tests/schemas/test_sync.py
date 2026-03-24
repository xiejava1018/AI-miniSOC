"""
同步Schema测试
"""
import pytest
from app.schemas.sync import SyncTaskCreate, SyncTaskResponse, WebhookPayload
from datetime import datetime


def test_sync_task_response_schema():
    """测试同步任务响应schema"""
    data = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "sync_type": "manual",
        "status": "completed",
        "total_count": 50,
        "created_count": 10,
        "updated_count": 40,
        "failed_count": 0,
        "started_at": "2026-03-24T10:00:00Z",
        "completed_at": "2026-03-24T10:05:00Z",
        "created_at": "2026-03-24T10:00:00Z"
    }

    schema = SyncTaskResponse(**data)
    assert schema.sync_type == "manual"
    assert schema.status == "completed"
    assert schema.total_count == 50
    assert schema.progress == "100%"


def test_webhook_payload_schema():
    """测试Webhook payload schema"""
    data = {
        "agent_id": "001",
        "agent_name": "server-01",
        "rule_id": "504",
        "alert": {
            "agent": {"id": "001", "name": "server-01"},
            "rule": {"id": "504", "level": 3}
        }
    }

    schema = WebhookPayload(**data)
    assert schema.agent_id == "001"
    assert schema.agent_name == "server-01"
    assert schema.rule_id == "504"


def test_sync_task_create_schema():
    """测试创建同步任务schema"""
    data = {
        "sync_type": "manual",
        "status": "pending"
    }

    schema = SyncTaskCreate(**data)
    assert schema.sync_type == "manual"
    assert schema.status == "pending"


def test_sync_task_progress_calculation():
    """测试进度计算"""
    data = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "sync_type": "manual",
        "status": "running",
        "total_count": 100,
        "created_count": 30,
        "updated_count": 20,
        "failed_count": 5,
        "created_at": "2026-03-24T10:00:00Z"
    }

    schema = SyncTaskResponse(**data)
    # (30 + 20 + 5) / 100 = 55%
    assert schema.progress == "55%"


def test_sync_task_progress_zero_total():
    """测试total_count为0时的进度计算"""
    data = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "sync_type": "manual",
        "status": "pending",
        "total_count": 0,
        "created_count": 0,
        "updated_count": 0,
        "failed_count": 0,
        "created_at": "2026-03-24T10:00:00Z"
    }

    schema = SyncTaskResponse(**data)
    assert schema.progress == "0%"


def test_webhook_payload_minimal():
    """测试最小webhook payload"""
    data = {
        "agent_id": "001"
    }

    schema = WebhookPayload(**data)
    assert schema.agent_id == "001"
    assert schema.agent_name is None
    assert schema.rule_id is None
    assert schema.alert is None
