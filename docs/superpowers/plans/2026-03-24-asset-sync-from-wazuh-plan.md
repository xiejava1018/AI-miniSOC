# 资产从Wazuh同步 - 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现从Wazuh SIEM系统同步资产信息到AI-miniSOC平台，支持手动触发、Webhook实时触发和定时兜底同步。

**Architecture:** 采用FastAPI后端服务处理同步逻辑，通过Wazuh Integrator模块实现Webhook实时触发，使用后台任务处理长时间同步操作，数据库记录同步历史和变更日志。

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2.0, PostgreSQL, Vue.js 3, Element Plus, httpx

---

## 文件结构映射

### 新建文件
```
backend/
├── app/models/
│   ├── sync_task.py                    # 同步任务模型
│   └── asset_change_log.py             # 资产变更日志模型
├── app/schemas/
│   └── sync.py                         # 同步相关schemas
├── app/services/
│   └── asset_enrichment.py             # 资产详细信息补充服务
├── app/api/
│   ├── sync.py                         # 同步API端点
│   └── webhooks.py                     # Webhook接收端点
└── migrations/
    └── versions/XXXX_add_sync_tables.py # 数据库迁移脚本

frontend/
├── src/api/
│   └── sync.ts                         # 同步API客户端
└── src/views/
    ├── SyncHistory.vue                 # 同步历史页面
    └── SyncTaskDetail.vue              # 同步任务详情页面
```

### 修改文件
```
backend/
├── app/models/asset.py                 # 添加data_source等字段
├── app/services/asset_sync.py          # 增强同步服务
├── app/api/assets.py                   # 添加手动同步端点
├── app/core/config.py                  # 添加WAZUH_WEBHOOK_KEY配置
└── app/models/__init__.py              # 导出新模型

frontend/
└── src/views/Assets.vue                # 添加同步按钮
```

---

## Task 1: 数据库模型 - 同步任务表

**Files:**
- Create: `app/models/sync_task.py`
- Test: `tests/models/test_sync_task.py` (create if not exists)

- [ ] **Step 1: Create test file and write failing test**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/xiejava/AIproject/AI-miniSOC/src/backend && pytest tests/models/test_sync_task.py -v`

Expected: `ModuleNotFoundError: No module named 'app.models.sync_task'`

- [ ] **Step 3: Create SyncTask model**

```python
# app/models/sync_task.py
"""
同步任务模型
"""
from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.models.base import Base


class SyncTask(Base):
    """同步任务表"""
    __tablename__ = "sync_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    sync_type = Column(String(20), nullable=False)  # 'manual', 'webhook', 'scheduled'
    status = Column(String(20), nullable=False, default="pending")  # 'pending', 'running', 'completed', 'failed'
    total_count = Column(Integer, nullable=False, default=0)
    created_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<SyncTask(id={self.id}, type={self.sync_type}, status={self.status})>"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/xiejava/AIproject/AI-miniSOC/src/backend && pytest tests/models/test_sync_task.py -v`

Expected: `PASSED`

- [ ] **Step 5: Update models __init__.py**

```python
# app/models/__init__.py
from app.models.base import Base
from app.models.user import User, Role
from app.models.asset import Asset
from app.models.asset_port import AssetPort
from app.models.asset_tag import AssetTag
from app.models.incident import Incident
from app.models.sync_task import SyncTask  # Add this line
from app.models.asset_change_log import AssetChangeLog  # Will add in next task

__all__ = ["Base", "User", "Role", "Asset", "AssetPort", "AssetTag", "Incident", "SyncTask", "AssetChangeLog"]
```

- [ ] **Step 6: Commit**

```bash
cd /home/xiejava/AIproject/AI-miniSOC
git add src/backend/app/models/sync_task.py src/backend/app/models/__init__.py tests/models/test_sync_task.py
git commit -m "feat: add SyncTask model for tracking sync operations

- Add sync_tasks table with status tracking
- Support manual, webhook, and scheduled sync types
- Add counters for created/updated/failed assets

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: 数据库模型 - 资产变更日志表

**Files:**
- Create: `app/models/asset_change_log.py`
- Test: `tests/models/test_asset_change_log.py`

- [ ] **Step 1: Write failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/models/test_asset_change_log.py -v`

Expected: `ModuleNotFoundError: No module named 'app.models.asset_change_log'`

- [ ] **Step 3: Create AssetChangeLog model**

```python
# app/models/asset_change_log.py
"""
资产变更日志模型
"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.models.base import Base


class AssetChangeLog(Base):
    """资产变更日志表"""
    __tablename__ = "asset_change_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    asset_id = Column(UUID(as_uuid=True), ForeignKey('soc_assets.id', ondelete='CASCADE'), nullable=False)
    sync_task_id = Column(UUID(as_uuid=True), ForeignKey('sync_tasks.id', ondelete='SET NULL'))
    change_type = Column(String(20), nullable=False)  # 'created', 'updated', 'status_changed'
    field_name = Column(String(50))
    old_value = Column(Text)
    new_value = Column(Text)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AssetChangeLog(id={self.id}, asset_id={self.asset_id}, type={self.change_type})>"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/models/test_asset_change_log.py -v`

Expected: `PASSED`

- [ ] **Step 5: Update models __init__.py to import AssetChangeLog**

```python
# app/models/__init__.py
from app.models.asset_change_log import AssetChangeLog
```

- [ ] **Step 6: Commit**

```bash
git add src/backend/app/models/asset_change_log.py src/backend/app/models/__init__.py tests/models/test_asset_change_log.py
git commit -m "feat: add AssetChangeLog model for tracking asset changes

- Track field-level changes to assets
- Link changes to sync tasks for traceability
- Support created, updated, and status_changed types

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: 扩展Asset模型

**Files:**
- Modify: `app/models/asset.py:1-45`
- Test: `tests/models/test_asset.py` (update existing tests)

- [ ] **Step 1: Write test for new fields**

```python
# tests/models/test_asset.py (add to existing file)
def test_asset_with_wazuh_fields(db_session):
    """测试资产的Wazuh相关字段"""
    from datetime import datetime, timezone

    asset = Asset(
        name="test-server",
        asset_ip="192.168.1.100",
        data_source="wazuh",
        last_synced_at=datetime.now(timezone.utc),
        os_name="Ubuntu",
        os_version="22.04",
        hardware_info={"cpu": "4 cores", "memory": "8GB"}
    )
    db_session.add(asset)
    db_session.commit()
    db_session.refresh(asset)

    assert asset.data_source == "wazuh"
    assert asset.last_synced_at is not None
    assert asset.os_name == "Ubuntu"
    assert asset.os_version == "22.04"
    assert asset.hardware_info["cpu"] == "4 cores"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/models/test_asset.py::test_asset_with_wazuh_fields -v`

Expected: `TypeError: Asset() got an unexpected keyword argument 'data_source'`

- [ ] **Step 3: Add new fields to Asset model**

```python
# app/models/asset.py - add after line 28 (before name field)

from sqlalchemy.dialects.postgresql import JSONB  # Add to imports

class Asset(Base):
    """资产表"""
    # ... existing fields ...

    # Add these new fields
    data_source = Column(String(20), default="manual")  # 'wazuh', 'manual'
    last_synced_at = Column(DateTime(timezone=True))
    os_name = Column(String(100))
    os_version = Column(String(100))
    hardware_info = Column(JSONB)

    # existing fields continue...
    name = Column(String(255))
    # ... rest of existing fields ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/models/test_asset.py::test_asset_with_wazuh_fields -v`

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/models/asset.py tests/models/test_asset.py
git commit -m "feat: add Wazuh sync fields to Asset model

- Add data_source to track asset origin
- Add last_synced_at for sync timestamp
- Add os_name, os_version for OS info
- Add hardware_info (JSONB) for system specs

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 4: 创建同步Schema

**Files:**
- Create: `app/schemas/sync.py`
- Test: `tests/schemas/test_sync.py`

- [ ] **Step 1: Write failing test**

```python
# tests/schemas/test_sync.py
import pytest
from app.schemas.sync import SyncTaskCreate, SyncTaskResponse
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
    from app.schemas.sync import WebhookPayload

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/schemas/test_sync.py -v`

Expected: `ModuleNotFoundError: No module named 'app.schemas.sync'`

- [ ] **Step 3: Create sync schemas**

```python
# app/schemas/sync.py
"""
同步相关Schemas
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, Dict, Any


class SyncTaskBase(BaseModel):
    """同步任务基础schema"""
    sync_type: str = Field(..., description="同步类型: manual, webhook, scheduled")
    status: str = Field(default="pending", description="状态: pending, running, completed, failed")


class SyncTaskCreate(SyncTaskBase):
    """创建同步任务"""
    pass


class SyncTaskResponse(SyncTaskBase):
    """同步任务响应"""
    id: str
    total_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    failed_count: int = 0
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    @property
    def progress(self) -> str:
        """计算进度百分比"""
        if self.total_count == 0:
            return "0%"
        completed = self.created_count + self.updated_count + self.failed_count
        return f"{int(completed / self.total_count * 100)}%"

    class Config:
        from_attributes = True


class SyncTaskList(BaseModel):
    """同步任务列表"""
    total: int
    items: list[SyncTaskResponse]


class ManualSyncResponse(BaseModel):
    """手动同步响应"""
    task_id: str
    status: str
    message: str


class WebhookPayload(BaseModel):
    """Webhook payload"""
    agent_id: str
    agent_name: Optional[str] = None
    rule_id: Optional[str] = None
    alert: Optional[Dict[str, Any]] = None


class WebhookResponse(BaseModel):
    """Webhook响应"""
    success: bool
    message: str
    asset_id: Optional[str] = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/schemas/test_sync.py -v`

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/schemas/sync.py tests/schemas/test_sync.py
git commit -m "feat: add sync-related schemas

- Add SyncTaskCreate, SyncTaskResponse schemas
- Add WebhookPayload and response schemas
- Add progress calculation property

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 5: 增强AssetSyncService

**Files:**
- Modify: `app/services/asset_sync.py:14-120`
- Test: `tests/services/test_asset_sync.py`

- [ ] **Step 1: Write test for enhanced sync service**

```python
# tests/services/test_asset_sync.py
import pytest
from app.services.asset_sync import AssetSyncService
from app.models.sync_task import SyncTask
from app.models.asset_change_log import AssetChangeLog

def test_sync_with_tracking(db_session, mock_wazuh_client):
    """测试带追踪的同步"""
    service = AssetSyncService(db_session)

    task = service.sync_from_wazuh_with_tracking("manual")

    assert task.sync_type == "manual"
    assert task.status in ["completed", "failed"]
    assert task.started_at is not None
    if task.status == "completed":
        assert task.completed_at is not None

def test_webhook_sync_single_agent(db_session, mock_wazuh_client):
    """测试Webhook同步单个agent"""
    service = AssetSyncService(db_session)

    asset = service.sync_single_agent_webhook("001")

    assert asset is not None
    assert asset.wazuh_agent_id == "001"
    assert asset.data_source == "wazuh"
    assert asset.last_synced_at is not None

    # 检查是否创建了变更日志
    change_log = db_session.query(AssetChangeLog).filter(
        AssetChangeLog.asset_id == asset.id
    ).first()
    assert change_log is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_asset_sync.py -v`

Expected: `AttributeError: 'AssetSyncService' object has no attribute 'sync_from_wazuh_with_tracking'`

- [ ] **Step 3: Add new methods to AssetSyncService**

```python
# app/services/asset_sync.py - add after existing methods

from datetime import datetime, timezone
from app.models.sync_task import SyncTask
from app.models.asset_change_log import AssetChangeLog
from app.models import Asset

class AssetSyncService:
    # ... existing methods ...

    def sync_from_wazuh_with_tracking(self, sync_type: str = "manual") -> SyncTask:
        """带追踪的同步"""
        # 创建同步任务记录
        task = SyncTask(
            sync_type=sync_type,
            status="running",
            started_at=datetime.now(timezone.utc)
        )
        self.db.add(task)
        self.db.commit()

        try:
            # 执行同步
            result = self.sync_from_wazuh()

            # 更新任务状态
            task.status = "completed"
            task.total_count = result["total"]
            task.created_count = result["created"]
            task.updated_count = result["updated"]
            task.failed_count = result["failed"]
            task.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)
            task.completed_at = datetime.now(timezone.utc)
            self.db.rollback()
            raise

        self.db.commit()
        self.db.refresh(task)
        return task

    def sync_single_agent_webhook(self, agent_id: str) -> Asset:
        """Webhook触发的单个agent同步"""
        agent = wazuh_client.get_agent_info(agent_id)
        asset_data = self._map_agent_to_asset(agent)

        # 检查是否已存在
        existing = self.db.query(Asset).filter(
            Asset.wazuh_agent_id == agent_id
        ).first()

        if existing:
            # 智能合并
            old_status = existing.asset_status
            existing.asset_status = asset_data["asset_status"]
            existing.wazuh_agent_id = asset_data["wazuh_agent_id"]
            existing.last_synced_at = datetime.now(timezone.utc)

            # 记录状态变更
            if old_status != existing.asset_status:
                self._log_change(
                    existing.id,
                    "status_changed",
                    "asset_status",
                    old_status,
                    existing.asset_status,
                    None
                )
        else:
            # 创建新资产
            asset = Asset(**asset_data)
            asset.data_source = "wazuh"
            asset.last_synced_at = datetime.now(timezone.utc)
            self.db.add(asset)
            self.db.flush()

            self._log_change(asset.id, "created", None, None, None)
            existing = asset

        self.db.commit()
        self.db.refresh(existing)
        return existing

    def _log_change(self, asset_id: str, change_type: str,
                    field_name: str, old_value: str, new_value: str,
                    sync_task_id: str = None):
        """记录变更日志"""
        log = AssetChangeLog(
            asset_id=asset_id,
            sync_task_id=sync_task_id,
            change_type=change_type,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value
        )
        self.db.add(log)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_asset_sync.py -v`

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/backend/app/services/asset_sync.py tests/services/test_asset_sync.py
git commit -m "feat: enhance AssetSyncService with tracking and webhook support

- Add sync_from_wazuh_with_tracking for task tracking
- Add sync_single_agent_webhook for webhook-triggered sync
- Add _log_change method for change logging
- Implement smart merge for existing assets

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 6: 创建资产详细信息补充服务

**Files:**
- Create: `app/services/asset_enrichment.py`
- Test: `tests/services/test_asset_enrichment.py`

- [ ] **Step 1: Write failing test**

```python
# tests/services/test_asset_enrichment.py
import pytest
from app.services.asset_enrichment import AssetEnrichmentService

@pytest.mark.asyncio
async def test_enrich_single_asset(db_session, test_asset, mock_wazuh_client):
    """测试补充单个资产详细信息"""
    service = AssetEnrichmentService(db_session)

    await service.enrich_single_asset(test_asset.id)
    db_session.refresh(test_asset)

    assert test_asset.os_name is not None
    assert test_asset.os_version is not None
    assert test_asset.hardware_info is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_asset_enrichment.py -v`

Expected: `ModuleNotFoundError: No module named 'app.services.asset_enrichment'`

- [ ] **Step 3: Create enrichment service**

```python
# app/services/asset_enrichment.py
"""
资产详细信息补充服务
"""
import asyncio
import logging
from sqlalchemy.orm import Session
from app.models import Asset
from app.services.wazuh_client import wazuh_client

logger = logging.getLogger(__name__)


class AssetEnrichmentService:
    """资产详细信息补充服务"""

    def __init__(self, db: Session):
        self.db = db

    async def enrich_new_assets(self, asset_ids: list[str]):
        """补充新创建资产的详细信息"""
        for asset_id in asset_ids:
            try:
                await self.enrich_single_asset(asset_id)
            except Exception as e:
                logger.error(f"Failed to enrich asset {asset_id}: {e}")

    async def enrich_single_asset(self, asset_id: str):
        """补充单个资产的详细信息"""
        asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset or not asset.wazuh_agent_id:
            return

        try:
            # 获取syscollector数据
            sysinfo = await asyncio.to_thread(
                wazuh_client.get_agent_sysinfo,
                asset.wazuh_agent_id
            )

            # 更新字段（不覆盖已存在的值）
            if sysinfo.get("os") and not asset.os_name:
                asset.os_name = sysinfo["os"].get("name")

            if sysinfo.get("os") and not asset.os_version:
                asset.os_version = sysinfo["os"].get("version")

            hardware = {
                "cpu": sysinfo.get("cpu", {}),
                "memory": sysinfo.get("memory", {})
            }
            if not asset.hardware_info:
                asset.hardware_info = hardware

            self.db.commit()

        except Exception as e:
            logger.error(f"Failed to get sysinfo for {asset_id}: {e}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/services/test_asset_enrichment.py -v`

Expected: `PASSED`

- [ ] **Step 5: Add get_agent_sysinfo method to WazuhClient**

```python
# app/services/wazuh_client.py - add new method

def get_agent_sysinfo(self, agent_id: str) -> dict:
    """获取agent系统信息"""
    data = self._request("GET", f"/syscollector/{agent_id}/hardware")
    return data.get("data", {})
```

- [ ] **Step 6: Commit**

```bash
git add src/backend/app/services/asset_enrichment.py src/backend/app/services/wazuh_client.py tests/services/test_asset_enrichment.py
git commit -m "feat: add asset enrichment service for detailed info

- Add AssetEnrichmentService for async enrichment
- Add get_agent_sysinfo to WazuhClient
- Enrich OS name, version, and hardware info
- Don't overwrite existing manual fields

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 7: 创建同步API端点

**Files:**
- Create: `app/api/sync.py`
- Modify: `app/main.py` (add router)
- Test: `tests/api/test_sync.py`

- [ ] **Step 1: Write failing test**

```python
# tests/api/test_sync.py
import pytest
from fastapi.testclient import TestClient

def test_manual_sync(client, db_session):
    """测试手动同步"""
    response = client.post("/api/v1/assets/sync/manual")

    assert response.status_code == 200
    data = response.json()
    assert "task_id" in data
    assert data["status"] == "pending"

def test_get_sync_task(client, db_session, test_sync_task):
    """测试查询同步任务"""
    response = client.get(f"/api/v1/sync/tasks/{test_sync_task.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_sync_task.id)

def test_list_sync_tasks(client, db_session):
    """测试查询同步任务列表"""
    response = client.get("/api/v1/sync/tasks")

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_sync.py -v`

Expected: `404 Not Found`

- [ ] **Step 3: Create sync API router**

```python
# app/api/sync.py
"""
同步API端点
"""
from fastapi import APIRouter, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.sync import (
    ManualSyncResponse,
    SyncTaskResponse,
    SyncTaskList
)
from app.services.asset_sync import AssetSyncService
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("/tasks/manual", response_model=ManualSyncResponse)
async def manual_sync(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """手动触发全量同步"""
    sync_service = AssetSyncService(db)

    # 创建任务并立即返回
    task = sync_service.sync_from_wazuh_with_tracking("manual")

    return ManualSyncResponse(
        task_id=str(task.id),
        status=task.status,
        message="同步任务已创建"
    )


@router.get("/tasks/{task_id}", response_model=SyncTaskResponse)
async def get_sync_task(
    task_id: str,
    db: Session = Depends(get_db)
):
    """查询同步任务进度"""
    from app.models.sync_task import SyncTask

    task = db.query(SyncTask).filter(SyncTask.id == task_id).first()
    if not task:
        from fastapi import HTTPException
        raise HTTPException(404, "同步任务不存在")

    return SyncTaskResponse.model_validate(task)


@router.get("/tasks", response_model=SyncTaskList)
async def list_sync_tasks(
    skip: int = 0,
    limit: int = 20,
    status: str = None,
    db: Session = Depends(get_db)
):
    """查询同步任务列表"""
    from app.models.sync_task import SyncTask

    query = db.query(SyncTask)

    if status:
        query = query.filter(SyncTask.status == status)

    total = query.count()
    tasks = query.order_by(SyncTask.created_at.desc()).offset(skip).limit(limit).all()

    return SyncTaskList(
        total=total,
        items=[SyncTaskResponse.model_validate(t) for t in tasks]
    )
```

- [ ] **Step 4: Register router in main.py**

```python
# app/main.py - add to imports and router registration

from app.api.sync import router as sync_router  # Add import

# Add to router registration
app.include_router(sync_router, prefix="/api/v1", tags=["sync"])
```

- [ ] **Step 5: Update assets API to use sync service**

```python
# app/api/assets.py - modify sync endpoint

@router.post("/sync/from-wazuh")
async def sync_from_wazuh(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """从Wazuh同步资产（保留兼容性）"""
    sync_service = AssetSyncService(db)
    task = sync_service.sync_from_wazuh_with_tracking("manual")

    return {
        "message": "同步任务已创建",
        "task_id": str(task.id)
    }
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/api/test_sync.py -v`

Expected: `PASSED`

- [ ] **Step 7: Commit**

```bash
git add src/backend/app/api/sync.py src/backend/app/main.py src/backend/app/api/assets.py tests/api/test_sync.py
git commit -m "feat: add sync API endpoints

- Add POST /api/v1/assets/sync/manual for manual sync
- Add GET /api/v1/sync/tasks/{id} for task progress
- Add GET /api/v1/sync/tasks for task history
- Update existing sync endpoint to use new service

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 8: 创建Webhook接收端点

**Files:**
- Create: `app/api/webhooks.py`
- Modify: `app/core/config.py` (add WEBHOOK_KEY)
- Modify: `app/main.py` (add router)
- Test: `tests/api/test_webhooks.py`

- [ ] **Step 1: Write failing test**

```python
# tests/api/test_webhooks.py
import pytest
from fastapi.testclient import TestClient

def test_webhook_no_auth(client):
    """测试无认证的webhook请求"""
    response = client.post("/api/v1/webhooks/wazuh", json={
        "agent_id": "001",
        "agent_name": "test-server"
    })

    assert response.status_code == 401

def test_webhook_with_valid_key(client, mock_wazuh_client):
    """测试有效API key的webhook请求"""
    response = client.post(
        "/api/v1/webhooks/wazuh",
        json={
            "agent_id": "001",
            "agent_name": "test-server",
            "rule_id": "504"
        },
        headers={"X-API-Key": "test-webhook-key"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_webhooks.py -v`

Expected: `404 Not Found`

- [ ] **Step 3: Add webhook config to settings**

```python
# app/core/config.py - add to Settings class

class Settings(BaseSettings):
    # ... existing settings ...

    # Wazuh Webhook配置
    WAZUH_WEBHOOK_KEY: str = "change-this-in-production"
    WAZUH_WEBHOOK_ALLOWED_IPS: str = "192.168.0.30,192.168.0.40"

    @property
    def webhook_allowed_ips_list(self) -> list[str]:
        """解析IP白名单"""
        return [ip.strip() for ip in self.WAZUH_WEBHOOK_ALLOWED_IPS.split(",")]
```

- [ ] **Step 4: Create webhook router**

```python
# app/api/webhooks.py
"""
Webhook接收端点
"""
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas.sync import WebhookPayload, WebhookResponse
from app.services.asset_sync import AssetSyncService
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def verify_webhook_request(request: Request):
    """验证webhook请求"""
    # 验证IP
    client_ip = request.client.host
    if client_ip not in settings.webhook_allowed_ips_list:
        logger.warning(f"Webhook request from unauthorized IP: {client_ip}")
        raise HTTPException(403, "IP not allowed")

    # 验证API Key
    api_key = request.headers.get("X-API-Key")
    if not api_key or api_key != settings.WAZUH_WEBHOOK_KEY:
        logger.warning("Webhook request with invalid API key")
        raise HTTPException(401, "Invalid API key")

    return True


@router.post("/wazuh", response_model=WebhookResponse)
async def wazuh_webhook(
    payload: WebhookPayload,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_webhook_request)
):
    """接收Wazuh webhook"""
    agent_id = payload.agent_id

    if not agent_id:
        raise HTTPException(400, "Missing agent_id")

    try:
        sync_service = AssetSyncService(db)
        asset = sync_service.sync_single_agent_webhook(agent_id)

        logger.info(f"Webhook sync successful for agent {agent_id}")

        return WebhookResponse(
            success=True,
            message="Agent同步成功",
            asset_id=str(asset.id)
        )

    except Exception as e:
        logger.error(f"Webhook sync failed for agent {agent_id}: {e}")
        # 返回成功避免Wazuh重试
        return WebhookResponse(
            success=False,
            message=str(e)
        )
```

- [ ] **Step 5: Register router in main.py**

```python
# app/main.py
from app.api.webhooks import router as webhooks_router

app.include_router(webhooks_router, prefix="/api/v1")
```

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/api/test_webhooks.py -v`

Expected: `PASSED`

- [ ] **Step 7: Commit**

```bash
git add src/backend/app/api/webhooks.py src/backend/app/core/config.py src/backend/app/main.py tests/api/test_webhooks.py
git commit -m "feat: add Wazuh webhook receiver endpoint

- Add POST /api/v1/webhooks/wazuh endpoint
- Implement IP whitelist + API key authentication
- Link webhook to single agent sync
- Return success even on failure to prevent Wazuh retries

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 9: 创建数据库迁移脚本

**Files:**
- Create: Use Alembic to generate migration
- Run: Apply migration

- [ ] **Step 1: Generate Alembic migration**

```bash
cd /home/xiejava/AIproject/AI-miniSOC/src/backend

# Generate migration
source venv/bin/activate
alembic revision --autogenerate -m "add sync tables and asset wazuh fields"
```

- [ ] **Step 2: Review generated migration**

Check: `alembic/versions/XXXX_add_sync_tables_and_asset_wazuh_fields.py`

Ensure it includes:
- Create sync_tasks table
- Create asset_change_logs table
- Add data_source, last_synced_at, os_name, os_version, hardware_info to soc_assets
- Create indexes

- [ ] **Step 3: Apply migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade -> <revision_id>, add sync tables and asset wazuh fields`

- [ ] **Step 4: Verify database schema**

```bash
python -c "
from app.database import engine
from sqlalchemy import inspect

inspector = inspect(engine)
tables = inspector.get_table_names()
print('Tables:', tables)

if 'sync_tasks' in tables:
    print('sync_tasks columns:', [c['name'] for c in inspector.get_columns('sync_tasks')])
if 'asset_change_logs' in tables:
    print('asset_change_logs columns:', [c['name'] for c in inspector.get_columns('asset_change_logs')])
"
```

Expected: Shows sync_tasks and asset_change_logs tables with correct columns

- [ ] **Step 5: Commit migration**

```bash
git add alembic/versions/
git commit -m "feat: add database migration for sync feature

- Create sync_tasks table for tracking sync operations
- Create asset_change_logs table for audit trail
- Add Wazuh-related fields to assets table
- Add indexes for performance

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 10: 前端 - 创建同步API客户端

**Files:**
- Create: `src/api/sync.ts`

- [ ] **Step 1: Create sync API client**

```typescript
// src/api/sync.ts
/**
 * 同步相关API
 */
import apiClient from './client'

export interface SyncTask {
  id: string
  sync_type: string
  status: string
  total_count: number
  created_count: number
  updated_count: number
  failed_count: number
  error_message?: string
  started_at?: string
  completed_at?: string
  created_at: string
  progress?: string
}

export interface ManualSyncResponse {
  task_id: string
  status: string
  message: string
}

export interface SyncTaskList {
  total: number
  items: SyncTask[]
}

export const syncApi = {
  // 手动同步
  manualSync: () =>
    apiClient.post<ManualSyncResponse>('/assets/sync/manual', {}),

  // 查询任务进度
  getTask: (taskId: string) =>
    apiClient.get<SyncTask>(`/sync/tasks/${taskId}`),

  // 查询任务列表
  listTasks: (params?: { skip?: number; limit?: number; status?: string }) =>
    apiClient.get<SyncTaskList>('/sync/tasks', params)
}
```

- [ ] **Step 2: Export from index**

```typescript
// src/api/index.ts - add export
export * from './sync'
```

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/api/sync.ts src/frontend/src/api/index.ts
git commit -m "feat: add sync API client for frontend

- Add syncApi with manualSync, getTask, listTasks
- Define TypeScript interfaces for sync tasks
- Export from main API module

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 11: 前端 - 增强资产列表页

**Files:**
- Modify: `src/views/Assets.vue`

- [ ] **Step 1: Add sync button to Assets page**

```vue
<!-- src/views/Assets.vue - modify template -->
<template>
  <div class="assets-page">
    <el-page-header @back="goBack" title="返回">
      <template #content>
        <span>资产管理</span>
      </template>
      <template #extra>
        <el-button
          type="primary"
          @click="handleManualSync"
          :loading="syncLoading"
        >
          <el-icon><Refresh /></el-icon>
          从Wazuh同步
        </el-button>
        <el-button @click="viewSyncHistory">
          同步历史
        </el-button>
      </template>
    </el-page-header>

    <!-- 显示最后同步时间 -->
    <el-alert
      v-if="lastSyncTime"
      type="info"
      :closable="false"
      style="margin-top: 10px"
    >
      最后同步时间: {{ formatDate(lastSyncTime) }}
    </el-alert>

    <!-- 现有资产列表内容... -->
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { syncApi } from '@/api'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'

const router = useRouter()
const syncLoading = ref(false)
const lastSyncTime = ref<string | null>(null)

async function handleManualSync() {
  syncLoading.value = true
  try {
    const result = await syncApi.manualSync()
    ElMessage.success('同步任务已创建')
    // 跳转到同步任务详情页
    router.push(`/sync-tasks/${result.task_id}`)
  } catch (error: any) {
    ElMessage.error(error.message || '创建同步任务失败')
  } finally {
    syncLoading.value = false
  }
}

function viewSyncHistory() {
  router.push('/sync-tasks')
}

function formatDate(dateStr: string) {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

function goBack() {
  router.back()
}
</script>
```

- [ ] **Step 2: Add sync tasks route**

```typescript
// src/router/index.ts - add route
{
  path: '/sync-tasks',
  name: 'SyncTasks',
  component: () => import('@/views/SyncHistory.vue')
},
{
  path: '/sync-tasks/:id',
  name: 'SyncTaskDetail',
  component: () => import('@/views/SyncTaskDetail.vue')
}
```

- [ ] **Step 3: Commit**

```bash
git add src/frontend/src/views/Assets.vue src/frontend/src/router/index.ts
git commit -m "feat: add manual sync button to assets page

- Add '从Wazuh同步' button in page header
- Show last sync time alert
- Add navigation to sync history
- Add sync task routes

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 12: 前端 - 创建同步历史页面

**Files:**
- Create: `src/views/SyncHistory.vue`

- [ ] **Step 1: Create sync history page**

```vue
<!-- src/views/SyncHistory.vue -->
<template>
  <div class="sync-history">
    <el-page-header @back="goBack" title="返回">
      <template #content>
        <span>同步历史</span>
      </template>
    </el-page-header>

    <el-card style="margin-top: 20px" v-loading="loading">
      <el-table :data="tasks" style="width: 100%">
        <el-table-column prop="sync_type" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="getTypeTag(row.sync_type)">
              {{ getTypeLabel(row.sync_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="getStatusTag(row.status)">
              {{ getStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="统计" width="300">
          <template #default="{ row }">
            总: {{ row.total_count }} |
            新增: {{ row.created_count }} |
            更新: {{ row.updated_count }} |
            失败: {{ row.failed_count }}
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="开始时间" width="180">
          <template #default="{ row }">
            {{ formatDate(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="viewDetail(row.id)">
              查看详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-pagination
        v-model:current-page="currentPage"
        v-model:page-size="pageSize"
        :total="total"
        @current-change="loadTasks"
        style="margin-top: 20px; text-align: right"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { syncApi, type SyncTask } from '@/api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const loading = ref(false)
const tasks = ref<SyncTask[]>([])
const total = ref(0)
const currentPage = ref(1)
const pageSize = ref(20)

onMounted(() => {
  loadTasks()
})

async function loadTasks() {
  loading.value = true
  try {
    const data = await syncApi.listTasks({
      skip: (currentPage.value - 1) * pageSize.value,
      limit: pageSize.value
    })
    tasks.value = data.items
    total.value = data.total
  } catch (error: any) {
    ElMessage.error(error.message || '加载同步历史失败')
  } finally {
    loading.value = false
  }
}

function viewDetail(taskId: string) {
  router.push(`/sync-tasks/${taskId}`)
}

function getTypeTag(type: string) {
  const tags: Record<string, string> = {
    manual: '',
    webhook: 'success',
    scheduled: 'warning'
  }
  return tags[type] || ''
}

function getTypeLabel(type: string) {
  const labels: Record<string, string> = {
    manual: '手动',
    webhook: 'Webhook',
    scheduled: '定时'
  }
  return labels[type] || type
}

function getStatusTag(status: string) {
  const tags: Record<string, string> = {
    pending: 'info',
    running: 'warning',
    completed: 'success',
    failed: 'danger'
  }
  return tags[status] || ''
}

function getStatusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: '待执行',
    running: '执行中',
    completed: '已完成',
    failed: '失败'
  }
  return labels[status] || status
}

function formatDate(dateStr: string) {
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

function goBack() {
  router.back()
}
</script>

<style scoped>
.sync-history {
  padding: 20px;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add src/frontend/src/views/SyncHistory.vue
git commit -m "feat: add sync history page

- Display sync tasks in table format
- Show sync type, status, and statistics
- Support pagination
- Add navigation to task detail

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 13: 前端 - 创建同步任务详情页面

**Files:**
- Create: `src/views/SyncTaskDetail.vue`

- [ ] **Step 1: Create sync task detail page**

```vue
<!-- src/views/SyncTaskDetail.vue -->
<template>
  <div class="sync-task-detail">
    <el-page-header @back="goBack" title="返回">
      <template #content>
        <span>同步任务详情</span>
      </template>
    </el-page-header>

    <el-card style="margin-top: 20px" v-loading="loading">
      <el-descriptions v-if="task" :column="2" border>
        <el-descriptions-item label="任务ID">
          {{ task.id }}
        </el-descriptions-item>
        <el-descriptions-item label="同步类型">
          <el-tag :type="getTypeTag(task.sync_type)">
            {{ getTypeLabel(task.sync_type) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="状态">
          <el-tag :type="getStatusTag(task.status)">
            {{ getStatusLabel(task.status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="进度">
          {{ task.progress || '0%' }}
        </el-descriptions-item>
        <el-descriptions-item label="总数">
          {{ task.total_count }}
        </el-descriptions-item>
        <el-descriptions-item label="新增">
          {{ task.created_count }}
        </el-descriptions-item>
        <el-descriptions-item label="更新">
          {{ task.updated_count }}
        </el-descriptions-item>
        <el-descriptions-item label="失败">
          {{ task.failed_count }}
        </el-descriptions-item>
        <el-descriptions-item label="开始时间">
          {{ formatDate(task.started_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="完成时间">
          {{ formatDate(task.completed_at) }}
        </el-descriptions-item>
        <el-descriptions-item label="错误信息" v-if="task.error_message" :span="2">
          <el-text type="danger">{{ task.error_message }}</el-text>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 自动刷新（进行中的任务） -->
    <el-alert
      v-if="task?.status === 'running'"
      type="info"
      :closable="false"
      style="margin-top: 20px"
    >
      任务执行中，页面将自动刷新...
    </el-alert>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { syncApi, type SyncTask } from '@/api'
import { ElMessage } from 'element-plus'

const router = useRouter()
const route = useRoute()
const loading = ref(false)
const task = ref<SyncTask | null>(null)
let refreshInterval: number | null = null

onMounted(() => {
  loadTask()
  // 如果任务在运行，每5秒刷新一次
  if (task.value?.status === 'running') {
    startAutoRefresh()
  }
})

onUnmounted(() => {
  stopAutoRefresh()
})

async function loadTask() {
  loading.value = true
  try {
    const taskId = route.params.id as string
    task.value = await syncApi.getTask(taskId)

    // 如果任务完成，停止自动刷新
    if (task.value.status !== 'running') {
      stopAutoRefresh()
    }
  } catch (error: any) {
    ElMessage.error(error.message || '加载任务详情失败')
  } finally {
    loading.value = false
  }
}

function startAutoRefresh() {
  refreshInterval = window.setInterval(() => {
    loadTask()
  }, 5000)
}

function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
}

function getTypeTag(type: string) {
  const tags: Record<string, string> = {
    manual: '',
    webhook: 'success',
    scheduled: 'warning'
  }
  return tags[type] || ''
}

function getTypeLabel(type: string) {
  const labels: Record<string, string> = {
    manual: '手动',
    webhook: 'Webhook',
    scheduled: '定时'
  }
  return labels[type] || type
}

function getStatusTag(status: string) {
  const tags: Record<string, string> = {
    pending: 'info',
    running: 'warning',
    completed: 'success',
    failed: 'danger'
  }
  return tags[status] || ''
}

function getStatusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: '待执行',
    running: '执行中',
    completed: '已完成',
    failed: '失败'
  }
  return labels[status] || status
}

function formatDate(dateStr?: string) {
  if (!dateStr) return '-'
  const date = new Date(dateStr)
  return date.toLocaleString('zh-CN')
}

function goBack() {
  router.back()
}
</script>

<style scoped>
.sync-task-detail {
  padding: 20px;
}
</style>
```

- [ ] **Step 2: Commit**

```bash
git add src/frontend/src/views/SyncTaskDetail.vue
git commit -m "feat: add sync task detail page

- Display task information in descriptions
- Show progress and statistics
- Auto-refresh for running tasks
- Show error messages if failed

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 14: Wazuh集成 - 创建集成脚本

**Files:**
- Create: `/var/ossec/integrations/custom-minisoc` (on Wazuh server)

**注意**: 此任务需要在Wazuh服务器上执行

- [ ] **Step 1: Create integration script on Wazuh server**

```bash
# SSH到Wazuh服务器
ssh xiejava@192.168.0.30

# 创建脚本
sudo tee /var/ossec/integrations/custom-minisoc << 'EOF'
#!/usr/bin/env python3
"""
Wazuh Integration Script for AI-miniSOC
触发资产同步Webhook
"""
import sys
import json
import httpx
import logging

logging.basicConfig(filename='/var/log/wazuh/integrations.log', level=logging.INFO)

def main():
    # 读取参数
    alert_file = sys.argv[1] if len(sys.argv) > 1 else None
    api_key = sys.argv[2] if len(sys.argv) > 2 else None
    hook_url = sys.argv[3] if len(sys.argv) > 3 else None

    if not alert_file or not hook_url:
        logging.error("Missing required parameters")
        sys.exit(1)

    # 解析alert
    try:
        with open(alert_file) as f:
            alert = json.load(f)
    except Exception as e:
        logging.error(f"Failed to read alert file: {e}")
        sys.exit(1)

    # 提取agent信息
    agent_id = alert.get('agent', {}).get('id')
    agent_name = alert.get('agent', {}).get('name')
    rule_id = alert.get('rule', {}).get('id')

    if not agent_id:
        logging.error("Agent ID not found in alert")
        sys.exit(1)

    # 调用miniSOC API
    try:
        payload = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "rule_id": rule_id,
            "alert": alert
        }

        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        response = httpx.post(
            hook_url,
            json=payload,
            headers=headers,
            timeout=5
        )

        if response.status_code == 200:
            logging.info(f"Webhook sent successfully for agent {agent_id}")
        else:
            logging.warning(f"Webhook returned {response.status_code}: {response.text}")

    except Exception as e:
        logging.error(f"Failed to send webhook: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
EOF

# 设置权限
sudo chmod 750 /var/ossec/integrations/custom-minisoc
sudo chown root:wazuh /var/ossec/integrations/custom-minisoc
```

- [ ] **Step 2: Generate secure API key**

```bash
# Generate API key
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Save the generated key - you'll need it for the next step.

- [ ] **Step 3: Configure Wazuh integration**

```bash
# Backup config
sudo cp /var/ossec/etc/ossec.conf /var/ossec/etc/ossec.conf.bak

# Add integration block
sudo tee -a /var/ossec/etc/ossec.conf << 'EOF'

  <!-- AI-miniSOC Integration -->
  <integration>
    <name>custom-minisoc</name>
    <hook_url>http://192.168.0.42:8000/api/v1/webhooks/wazuh</hook_url>
    <api_key>YOUR_GENERATED_API_KEY_HERE</api_key>
    <rule_id>504,506</rule_id>
    <alert_format>json</alert_format>
  </integration>
EOF

# Replace YOUR_GENERATED_API_KEY_HERE with the key from step 2
```

- [ ] **Step 4: Update backend environment variable**

```bash
# On backend server, add to .env
cd /home/xiejava/AIproject/AI-miniSOC/src/backend
echo "WAZUH_WEBHOOK_KEY=YOUR_GENERATED_API_KEY_HERE" >> .env
echo "WAZUH_WEBHOOK_ALLOWED_IPS=192.168.0.30,192.168.0.40" >> .env
```

- [ ] **Step 5: Restart Wazuh manager**

```bash
# On Wazuh server
sudo systemctl restart wazuh-manager
sudo systemctl status wazuh-manager
```

Expected: `active (running)`

- [ ] **Step 6: Test webhook**

```bash
# Check Wazuh logs for integration
sudo tail -f /var/log/wazuh/integrations.log

# Trigger a test (disconnect an agent temporarily)
# Or manually test the script
sudo -u wazuh /var/ossec/integrations/custom-minisoc /tmp/test_alert.json API_KEY http://192.168.0.42:8000/api/v1/webhooks/wazuh
```

- [ ] **Step 7: Commit documentation**

```bash
# Create documentation file
cat > /home/xiejava/AIproject/AI-miniSOC/docs/wazuh-integration-setup.md << 'EOF'
# Wazuh集成配置指南

## 概述

本文档说明如何在Wazuh服务器上配置自定义集成，实现agent状态变化时自动触发miniSOC资产同步。

## 步骤

1. **创建集成脚本**

   在Wazuh服务器上创建 `/var/ossec/integrations/custom-minisoc` 脚本（见实施计划Task 14）

2. **配置ossec.conf**

   在 `/var/ossec/etc/ossec.conf` 中添加integration配置块

3. **重启Wazuh manager**

   ```bash
   sudo systemctl restart wazuh-manager
   ```

4. **验证配置**

   检查日志: `sudo tail -f /var/log/wazuh/integrations.log`

## 故障排查

- 脚本无输出：检查脚本权限（750，root:wazuh）
- Webhook失败：检查网络连接和API key
- 无触发：检查rule_id配置（504,506）
EOF

git add docs/wazuh-integration-setup.md
git commit -m "docs: add Wazuh integration setup guide

- Document integration script setup
- Explain ossec.conf configuration
- Provide troubleshooting steps

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 15: 端到端测试

**Files:**
- Create: `tests/integration/test_e2e_sync.py`

- [ ] **Step 1: Write integration test**

```python
# tests/integration/test_e2e_sync.py
"""
端到端同步测试
"""
import pytest
from sqlalchemy.orm import Session
from app.services.asset_sync import AssetSyncService
from app.models.sync_task import SyncTask
from app.models.asset import Asset

def test_manual_sync_e2e(db: Session, mock_wazuh_api):
    """测试手动同步端到端流程"""
    # 创建同步服务
    service = AssetSyncService(db)

    # 执行同步
    task = service.sync_from_wazuh_with_tracking("manual")

    # 验证任务
    assert task.status == "completed"
    assert task.total_count > 0
    assert task.created_count + task.updated_count > 0

    # 验证资产已创建/更新
    assets = db.query(Asset).filter(
        Asset.data_source == "wazuh"
    ).all()
    assert len(assets) > 0

def test_webhook_sync_e2e(db: Session, client, mock_wazuh_api):
    """测试Webhook同步端到端流程"""
    response = client.post(
        "/api/v1/webhooks/wazuh",
        json={
            "agent_id": "001",
            "agent_name": "test-server",
            "rule_id": "504"
        },
        headers={"X-API-Key": "test-webhook-key"}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["asset_id"] is not None

    # 验证资产已创建
    asset = db.query(Asset).filter(
        Asset.wazuh_agent_id == "001"
    ).first()
    assert asset is not None
    assert asset.data_source == "wazuh"
```

- [ ] **Step 2: Run integration tests**

```bash
pytest tests/integration/test_e2e_sync.py -v
```

Expected: `PASSED`

- [ ] **Step 3: Manual testing checklist**

- [ ] 启动后端服务
- [ ] 启动前端服务
- [ ] 登录系统
- [ ] 点击"从Wazuh同步"按钮
- [ ] 查看同步任务详情页
- [ ] 验证资产列表更新
- [ ] 在Wazuh断开一个agent
- [ ] 检查miniSOC是否收到webhook
- [ ] 验证资产状态更新

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_e2e_sync.py
git commit -m "test: add end-to-end sync tests

- Test manual sync workflow
- Test webhook sync workflow
- Add manual testing checklist

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 16: 文档和清理

**Files:**
- Update: `README.md`
- Create: `CHANGELOG.md`

- [ ] **Step 1: Update README**

```markdown
# README.md - add section

## 资产同步

系统支持从Wazuh SIEM同步资产信息：

- **手动同步**: 在资产列表页点击"从Wazuh同步"按钮
- **实时同步**: Agent状态变化时自动触发（通过Webhook）
- **同步历史**: 查看所有同步任务的执行历史和详情

详见 [Wazuh集成配置指南](docs/wazuh-integration-setup.md)
```

- [ ] **Step 2: Create CHANGELOG entry**

```markdown
# CHANGELOG.md

## [Unreleased]

### Added
- 资产从Wazuh同步功能
  - 手动触发全量同步
  - Webhook实时触发单个agent同步
  - 同步任务历史和进度查询
  - 资产变更日志记录
  - 详细信息异步补充（操作系统、硬件）

### Changed
- 资产模型添加Wazuh相关字段（data_source, last_synced_at等）

### Fixed
- 修复前端API客户端307重定向问题
```

- [ ] **Step 3: Final commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: update documentation for sync feature

- Add asset sync section to README
- Create CHANGELOG entry for new features
- Link to Wazuh integration guide

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## 完成标准

- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] 手动测试清单完成
- [ ] Wazuh集成配置完成
- [ ] 文档更新完整
- [ ] 代码已提交到git

---

**实施计划完成！** 保存到 `docs/superpowers/plans/2026-03-24-asset-sync-from-wazuh-plan.md`
