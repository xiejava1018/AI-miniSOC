# 资产从Wazuh同步 - 设计方案

**日期**: 2026-03-24
**状态**: 已批准
**作者**: Claude Code

---

## 1. 概述

### 1.1 目标

实现从Wazuh SIEM系统同步资产信息到AI-miniSOC平台，支持：
- 手动触发全量同步
- Webhook实时触发单个agent同步
- 定时兜底全量同步
- 异步补充详细信息

### 1.2 范围

- **同步触发方式**：手动 + Webhook + 定时
- **同步信息**：基础信息（快速）+ 详细信息（异步补充）
- **冲突处理**：智能合并（状态/Agent ID覆盖，其他保留）
- **历史记录**：混合记录（数据库统计 + 变更日志 + 应用日志）

### 1.3 约束条件

- Wazuh agent数量：≤200个
- Wazuh服务器：192.168.0.30:55000, 192.168.0.40:55000
- 需要登录Wazuh服务器配置集成脚本

---

## 2. 架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         前端 (Vue.js)                        │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ 资产列表页  │  │ 手动同步按钮  │  │ 同步历史/进度    │  │
│  └─────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↓ HTTP
┌─────────────────────────────────────────────────────────────┐
│                      后端 API (FastAPI)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ /assets/sync │  │ /webhooks/   │  │ /sync/tasks/{id} │  │
│  │   手动触发   │  │   wazuh      │  │   查询进度       │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
          ↓                  ↓                    ↓
  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐
  │ 同步服务     │  │ Webhook处理  │  │ 后台任务队列     │
  │              │  │              │  │ (BackgroundTasks)│
  └──────────────┘  └──────────────┘  └──────────────────┘
          ↓                                  ↓
  ┌──────────────┐                  ┌──────────────────┐
  │ Wazuh Client │                  │ 详细信息补充     │
  │ (已存在)     │                  │ (异步)           │
  └──────────────┘                  └──────────────────┘
          ↓
┌─────────────────────────────────────────────────────────────┐
│                      Wazuh Server                            │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │ Agents API   │  │ Integrator   │                        │
│  │              │  │ (Webhook)    │                        │
│  └──────────────┘  └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

#### 手动全量同步流程
```
1. 用户点击"从Wazuh同步"按钮
2. 前端调用 POST /api/v1/assets/sync/manual
3. 后端创建sync_task记录（status=pending）
4. 后台任务执行：
   a. 调用Wazuh API获取所有agents
   b. 遍历agents，智能合并到数据库
   c. 记录变更日志
   d. 更新sync_task状态（status=completed）
5. 前端轮询 GET /api/v1/sync/tasks/{id} 查询进度
6. 完成后刷新资产列表
```

#### Webhook实时同步流程
```
1. Agent状态变化（Rule 504/506）
2. Wazuh触发Integrator，调用自定义脚本
3. 脚本解析alert，调用 POST /api/v1/webhooks/wazuh
4. 后端验证API Key + IP白名单
5. 创建sync_task（sync_type=webhook）
6. 获取agent详情并更新资产
7. 记录变更日志
8. 返回成功
```

---

## 3. 数据模型设计

### 3.1 新增数据表

#### sync_tasks - 同步任务表

```sql
CREATE TABLE sync_tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sync_type VARCHAR(20) NOT NULL,  -- 'manual', 'webhook', 'scheduled'
    status VARCHAR(20) NOT NULL,     -- 'pending', 'running', 'completed', 'failed'
    total_count INTEGER DEFAULT 0,
    created_count INTEGER DEFAULT 0,
    updated_count INTEGER DEFAULT 0,
    failed_count INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_sync_tasks_status ON sync_tasks(status);
CREATE INDEX idx_sync_tasks_created_at ON sync_tasks(created_at DESC);
```

#### asset_change_logs - 资产变更日志表

```sql
CREATE TABLE asset_change_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL REFERENCES soc_assets(id) ON DELETE CASCADE,
    sync_task_id UUID REFERENCES sync_tasks(id) ON DELETE SET NULL,
    change_type VARCHAR(20) NOT NULL,  -- 'created', 'updated', 'status_changed'
    field_name VARCHAR(50),
    old_value TEXT,
    new_value TEXT,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_asset_change_logs_asset_id ON asset_change_logs(asset_id);
CREATE INDEX idx_asset_change_logs_changed_at ON asset_change_logs(changed_at DESC);
```

### 3.2 资产模型扩展

在现有`Asset`模型中添加字段：

```python
# app/models/asset.py

class Asset(Base):
    # ... 现有字段 ...

    # 新增字段
    data_source = Column(String(20), default="manual")  # 'wazuh', 'manual'
    last_synced_at = Column(DateTime(timezone=True))   # 最后从Wazuh同步时间
    os_name = Column(String(100))                      # 操作系统名称
    os_version = Column(String(100))                   # 操作系统版本
    hardware_info = Column(JSONB)                      # 硬件信息（CPU、内存等）
```

---

## 4. API设计

### 4.1 同步API

#### POST /api/v1/assets/sync/manual

手动触发全量同步。

**请求**：无需请求体

**响应**：
```json
{
  "task_id": "uuid",
  "status": "pending",
  "message": "同步任务已创建"
}
```

#### GET /api/v1/sync/tasks/{task_id}

查询同步任务进度。

**响应**：
```json
{
  "id": "uuid",
  "sync_type": "manual",
  "status": "running",
  "total_count": 50,
  "created_count": 10,
  "updated_count": 35,
  "failed_count": 0,
  "started_at": "2026-03-24T10:00:00Z",
  "progress": "90%"
}
```

#### GET /api/v1/sync/tasks

查询同步历史列表。

**参数**：
- `skip`: 跳过条数
- `limit`: 返回条数
- `status`: 过滤状态

**响应**：
```json
{
  "total": 100,
  "items": [
    {
      "id": "uuid",
      "sync_type": "manual",
      "status": "completed",
      "total_count": 50,
      "created_count": 10,
      "updated_count": 40,
      "created_at": "2026-03-24T10:00:00Z"
    }
  ]
}
```

### 4.2 Webhook API

#### POST /api/v1/webhooks/wazuh

接收Wazuh Webhook，触发单个agent同步。

**验证**：
- IP白名单：192.168.0.30, 192.168.0.40
- API Key：Header `X-API-Key`

**请求体**：
```json
{
  "agent_id": "001",
  "agent_name": "server-01",
  "rule_id": "504",
  "alert": { ... }
}
```

**响应**：
```json
{
  "success": true,
  "message": "Agent同步成功",
  "asset_id": "uuid"
}
```

---

## 5. Wazuh集成配置

### 5.1 自定义集成脚本

**文件路径**: `/var/ossec/integrations/custom-minisoc`

**权限**：
```bash
chmod 750 /var/ossec/integrations/custom-minisoc
chown root:wazuh /var/ossec/integrations/custom-minisoc
```

**脚本内容**：
```python
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
```

### 5.2 Wazuh配置

**配置文件**: `/var/ossec/etc/ossec.conf`

**添加配置块**：
```xml
<ossec_config>
  <!-- AI-miniSOC Integration -->
  <integration>
    <name>custom-minisoc</name>
    <hook_url>http://192.168.0.42:8000/api/v1/webhooks/wazuh</hook_url>
    <api_key>YOUR_SECURE_API_KEY_HERE</api_key>
    <rule_id>504,506</rule_id>
    <alert_format>json</alert_format>
  </integration>
</ossec_config>
```

**配置说明**：
- `<rule_id>504,506</rule_id>`: 监听agent断开连接和停止事件
- 完成配置后需要重启Wazuh: `systemctl restart wazuh-manager`

---

## 6. 核心逻辑实现

### 6.1 同步服务增强

**文件**: `app/services/asset_sync.py`

**新增方法**：

```python
class AssetSyncService:
    # ... 现有方法 ...

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
                    existing.asset_status
                )
        else:
            # 创建新资产
            asset = Asset(**asset_data)
            asset.data_source = "wazuh"
            asset.last_synced_at = datetime.now(timezone.utc)
            self.db.add(asset)
            self.db.flush()

            self._log_change(asset.id, "created", None, None, None)

        self.db.commit()
        return existing or asset

    def _log_change(self, asset_id: str, change_type: str,
                    field_name: str, old_value: str, new_value: str):
        """记录变更日志"""
        log = AssetChangeLog(
            asset_id=asset_id,
            change_type=change_type,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value
        )
        self.db.add(log)
```

### 6.2 Webhook处理

**文件**: `app/api/webhooks.py` (新建)

```python
from fastapi import APIRouter, HTTPException, Request, Depends
from sqlalchemy.orm import Session
from app.services.asset_sync import AssetSyncService
from app.core.config import settings

router = APIRouter()

ALLOWED_IPS = ["192.168.0.30", "192.168.0.40"]
WEBHOOK_API_KEY = settings.WAZUH_WEBHOOK_KEY

def verify_webhook_request(request: Request):
    """验证webhook请求"""
    # 验证IP
    client_ip = request.client.host
    if client_ip not in ALLOWED_IPS:
        raise HTTPException(403, "IP not allowed")

    # 验证API Key
    api_key = request.headers.get("X-API-Key")
    if api_key != WEBHOOK_API_KEY:
        raise HTTPException(401, "Invalid API key")

    return True

@router.post("/wazuh")
async def wazuh_webhook(
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    _: bool = Depends(verify_webhook_request)
):
    """接收Wazuh webhook"""
    agent_id = payload.get("agent_id")
    agent_name = payload.get("agent_name")
    rule_id = payload.get("rule_id")

    if not agent_id:
        raise HTTPException(400, "Missing agent_id")

    try:
        sync_service = AssetSyncService(db)
        asset = sync_service.sync_single_agent_webhook(agent_id)

        return {
            "success": True,
            "message": "Agent同步成功",
            "asset_id": str(asset.id)
        }

    except Exception as e:
        logger.error(f"Webhook sync failed: {e}")
        # 返回成功避免Wazuh重试
        return {
            "success": False,
            "message": str(e)
        }
```

### 6.3 详细信息补充（异步）

**文件**: `app/services/asset_enrichment.py` (新建)

```python
import asyncio
from app.services.wazuh_client import wazuh_client
from app.models import Asset
from sqlalchemy.orm import Session

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

        # 获取syscollector数据
        try:
            sysinfo = wazuh_client.get_agent_sysinfo(asset.wazuh_agent_id)

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

---

## 7. 前端界面设计

### 7.1 资产列表页增强

**文件**: `src/views/Assets.vue`

**新增内容**：
```vue
<template>
  <div class="assets-page">
    <!-- 页面头部 -->
    <el-page-header>
      <template #extra>
        <el-button
          type="primary"
          @click="handleManualSync"
          :loading="syncLoading"
        >
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

    <!-- 现有资产列表... -->
  </div>
</template>

<script setup lang="ts">
async function handleManualSync() {
  try {
    const result = await syncApi.manualSync()
    ElMessage.success('同步任务已创建')
    // 跳转到同步历史页查看进度
    router.push(`/sync-tasks/${result.task_id}`)
  } catch (error) {
    ElMessage.error('创建同步任务失败')
  }
}
</script>
```

### 7.2 同步历史页面（新建）

**文件**: `src/views/SyncHistory.vue`

```vue
<template>
  <div class="sync-history">
    <el-page-header title="同步历史" @back="goBack" />

    <el-table :data="tasks" v-loading="loading">
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
      <el-table-column prop="created_at" label="开始时间" width="180" />
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-button link @click="viewDetail(row.id)">查看详情</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>
```

### 7.3 API客户端

**文件**: `src/api/sync.ts` (新建)

```typescript
import apiClient from './client'

export const syncApi = {
  // 手动同步
  manualSync: () =>
    apiClient.post<{ task_id: string; message: string }>('/assets/sync/manual', {}),

  // 查询任务进度
  getTask: (taskId: string) =>
    apiClient.get<SyncTask>(`/sync/tasks/${taskId}`),

  // 查询任务列表
  listTasks: (params?: { skip?: number; limit?: number; status?: string }) =>
    apiClient.get<{ items: SyncTask[]; total: number }>('/sync/tasks', params)
}
```

---

## 8. 安全性设计

### 8.1 Webhook验证

**双重验证机制**：

1. **IP白名单**：只允许Wazuh服务器IP访问
2. **API Key**：验证请求Header中的密钥

**实现**：
- FastAPI依赖注入验证
- 失败返回403/401，不处理请求

### 8.2 配置管理

**环境变量**（`.env`）：
```bash
# Wazuh Webhook配置
WAZUH_WEBHOOK_KEY=your_secure_random_key_here_min_32_chars
WAZUH_WEBHOOK_ALLOWED_IPS=192.168.0.30,192.168.0.40
```

**密钥生成**：
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 9. 错误处理

### 9.1 Wazuh API失败

**策略**：
- 记录错误日志
- 标记单个agent同步失败
- 继续处理其他agent
- 不影响整体同步任务

**实现**：
```python
try:
    agent = wazuh_client.get_agent_info(agent_id)
except httpx.HTTPError as e:
    logger.error(f"Failed to get agent {agent_id}: {e}")
    stats["failed"] += 1
    continue
```

### 9.2 Webhook调用失败

**策略**：
- Wazuh会自动重试（默认3次）
- 我们返回2xx成功，但内部记录失败
- 避免Wazuh无限重试导致压力

### 9.3 网络超时

**超时设置**：
- Wazuh API调用：10秒
- Webhook请求：5秒
- 使用异步httpx避免阻塞

---

## 10. 性能优化

### 10.1 批量处理

- 手动同步：遍历所有agents（≤200个）
- 数据库批量提交（每50个agent commit一次）

### 10.2 异步处理

- 详细信息补充使用后台任务
- 不阻塞主同步流程

### 10.3 缓存策略

- Wazuh JWT token缓存
- Agent信息缓存5分钟（可选）

---

## 11. 监控和日志

### 11.1 应用日志

**记录内容**：
- 同步任务开始/结束
- 每个agent的处理结果
- 错误堆栈和警告

**日志级别**：
- INFO：正常同步流程
- WARNING：部分失败
- ERROR：严重错误

### 11.2 数据库记录

**保留策略**：
- sync_tasks：保留90天
- asset_change_logs：保留30天

**定期清理**：
```python
# 定时任务（每天凌晨执行）
@app.on_event("startup")
async def schedule_cleanup():
    async def cleanup_old_records():
        while True:
            await asyncio.sleep(86400)  # 24小时
            cleanup_old_sync_tasks()
            cleanup_old_change_logs()

    asyncio.create_task(cleanup_old_records())
```

---

## 12. 测试计划

### 12.1 单元测试

- `AssetSyncService` 各个方法
- Webhook验证逻辑
- 智能合并逻辑

### 12.2 集成测试

- 手动同步完整流程
- Webhook接收和处理
- 错误场景（Wazuh API失败）

### 12.3 手动验证

1. **手动同步测试**：
   - 点击同步按钮
   - 查看任务进度
   - 验证资产数据

2. **Webhook测试**：
   - 在Wazuh服务器断开一个agent
   - 检查miniSOC是否收到webhook
   - 验证资产状态更新

3. **冲突处理测试**：
   - 手动修改资产名称
   - 再次同步
   - 验证名称保留，状态更新

---

## 13. 部署步骤

### 13.1 后端部署

1. 更新数据库模型
2. 运行迁移脚本创建新表
3. 部署新代码
4. 配置环境变量（`WAZUH_WEBHOOK_KEY`）

### 13.2 Wazuh配置

1. 登录Wazuh服务器（192.168.0.30）
2. 创建集成脚本
3. 修改`ossec.conf`添加integration配置
4. 设置脚本权限
5. 重启Wazuh manager

### 13.3 前端部署

1. 部署新代码
2. 验证同步按钮和历史页面

---

## 14. 未来扩展

### 14.1 可能的增强

- 支持同步agent的端口信息（通过syscollector）
- 支持同步vulnerability数据
- 支持多Wazuh集群
- 添加同步冲突解决策略配置

### 14.2 性能优化

- 对于大规模部署（>1000 agents），考虑使用消息队列
- 添加并行处理提高同步速度

---

## 附录

### A. Wazuh Agent状态说明

- **active**: Agent正在运行并连接到manager
- **disconnected**: Agent超过30分钟未发送心跳
- **never_connected**: Agent从未成功连接过

### B. 相关规则ID

- **504**: Wazuh agent disconnected
- **506**: Wazuh agent stopped

### C. 参考文档

- [Wazuh External API Integration](https://documentation.wazuh.com/current/user-manual/manager/integration-with-external-apis.html)
- [Wazuh Agent Life Cycle](https://documentation.wazuh.com/current/user-manual/agent/agent-enrollment/agent-life-cycle.html)
