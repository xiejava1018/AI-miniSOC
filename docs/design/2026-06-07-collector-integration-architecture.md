# AI-miniSOC 采集器集成架构设计

> 版本: v1.0
> 日期: 2026-06-07
> 状态: 架构设计完成，待开发实施
> 关联文档: [TP-Link 路由器 API 逆向分析](2026-06-07-tplink-router-integration.md)

---

## 1. 背景与目标

### 1.1 问题

AI-miniSOC 的安全数据（资产、漏洞、基线）目前存在以下问题：

| 问题 | 说明 |
|------|------|
| **数据来源耦合** | 资产采集逻辑（Wazuh Client、RouterClient）直接嵌入 AI-miniSOC 后端，新增数据源需改主服务代码 |
| **数据类型单一** | 目前只有资产数据，漏洞和基线是占位状态 |
| **部署不灵活** | 采集和主服务绑定，无法按需就近部署 |
| **扩展成本高** | 每增加一个数据源（交换机、云 API、扫描器），都要改 AI-miniSOC 代码并重启服务 |

### 1.2 目标

1. **解耦**：数据采集与安全管理完全分离，采集器作为独立服务运行
2. **可扩展**：新增数据源 = 新增一个 Collector 容器，AI-miniSOC 零改动
3. **多类型**：支持资产、漏洞、基线、端口等多种安全数据类型
4. **易运维**：每个 Collector 独立 Docker 容器，故障隔离、独立升级
5. **渐进式**：Phase 1 只做 TP-Link 资产采集，但架构预留全部扩展能力

### 1.3 设计原则

- **Collector 只管采**：采集原始数据，推送给 AI-miniSOC，不做业务逻辑
- **AI-miniSOC 只管存和分析**：接收数据、去重、变更记录、告警分析
- **统一协议**：所有 Collector 通过标准 REST API + API Key 与 AI-miniSOC 通信
- **共享框架**：通过 `collector-framework` 共享基类和客户端代码，减少重复开发

---

## 2. 整体架构

### 2.1 架构全景图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Network                            │
│                                                                  │
│  ┌──────────────────────────────────────────┐                   │
│  │         AI-miniSOC Backend (:8000)        │                   │
│  │                                           │                   │
│  │  ┌─────────────────────────────────────┐ │                   │
│  │  │  POST /api/v1/data/sync              │ │  ← 通用同步入口   │
│  │  │    ├─ AssetSyncHandler              │ │                   │
│  │  │    ├─ VulnerabilitySyncHandler      │ │                   │
│  │  │    ├─ BaselineSyncHandler           │ │                   │
│  │  │    └─ PortSyncHandler               │ │                   │
│  │  └─────────────────────────────────────┘ │                   │
│  │                                           │                   │
│  │  PostgreSQL    Wazuh    Loki    AI Engine  │                   │
│  └──────────────────────────▲───────────────┘                   │
│                             │                                    │
│              ┌──────────────┼──────────────┐                    │
│              │              │              │                     │
│  ┌───────────┴───┐  ┌──────┴──────┐  ┌───┴───────────┐        │
│  │ TP-Link       │  │ Wazuh       │  │ Nmap          │        │
│  │ Collector     │  │ Collector   │  │ Collector     │        │
│  │               │  │             │  │               │        │
│  │ 资产 ← 路由器  │  │ 资产/漏洞/  │  │ 资产/端口     │        │
│  │               │  │ 基线 ← Wazuh│  │ ← Nmap 扫描   │        │
│  │ 5min / 128MB  │  │ 10min/256MB │  │ 1h / 256MB   │        │
│  └───────────────┘  └─────────────┘  └───────────────┘        │
│                                                                  │
│  每个 Collector:                                                 │
│    ✅ 独立 Docker 容器                                           │
│    ✅ 独立配置 / 独立调度                                         │
│    ✅ 故障不传播                                                 │
│    ✅ 可独立升级 / 扩缩容                                         │
│    ✅ 共享 collector-framework 基类                              │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流

```
数据源                   Collector                    AI-miniSOC
───────                 ──────────                   ──────────

TP-Link 路由器  ──►  TP-Link Collector  ──┐
192.168.0.1          ├─ login (XOR+stok)   │
                     ├─ get_hosts()        │      ┌─ AssetSyncHandler
                     └─ transform()        ├─────►│  (去重/增量/变更记录)
                                           │      └─ 写入 soc_assets
Wazuh API  ──────►  Wazuh Collector  ──┐   │
192.168.0.30:55000   ├─ get_agents()    │   │      ┌─ VulnerabilitySyncHandler
                     ├─ get_vulns()     ├───┼─────►│  (CVE 关联/资产关联)
                     └─ get_sca()       │   │      └─ 写入 soc_vulnerabilities
                                           │
Nmap  ──────────►  Nmap Collector  ────┘        ┌─ PortSyncHandler
                    ├─ xml parse                │  (端口去重/服务识别)
                    └─ transform()              └─ 写入 soc_asset_ports
```

**核心流程**：

1. Collector 按配置的间隔定时执行（或单次触发）
2. Collector 连接数据源，采集原始数据
3. Collector 将原始数据转换为 AI-miniSOC 标准格式
4. Collector 调用 `POST /api/v1/data/sync` 推送数据
5. AI-miniSOC 根据数据类型路由到对应 Handler
6. Handler 执行去重、增量对比、变更记录，写入数据库

---

## 3. 数据类型定义

### 3.1 数据类型枚举

| 类型 | 英文 | 说明 | 现有表 |
|------|------|------|--------|
| 资产 | `asset` | 网络中的设备/主机信息 | `soc_assets` |
| 漏洞 | `vulnerability` | 资产上检测到的 CVE 漏洞 | 🆕 `soc_vulnerabilities` |
| 基线 | `baseline` | 安全配置合规检查结果 | 🆕 `soc_baselines` |
| 端口 | `port` | 资产开放端口和服务 | `soc_asset_ports` |

### 3.2 各类型数据字段规范

#### 3.2.1 资产（Asset）

Collector 推送的标准格式：

```json
{
  "source": "tplink-router",
  "data_type": "asset",
  "items": [
    {
      "name": "Redmi-Note-13-Pro",
      "asset_ip": "192.168.0.8",
      "mac_address": "9E:8D:2C:8C:3E:CF",
      "asset_type": "client",
      "asset_status": "online",
      "network_zone": "lan",
      "network_segment": "default",
      "criticality": "normal",
      "data_source": "tplink-router",
      "asset_description": "无线设备 | SSID: TP-LINK_3ED4 | 2.4GHz | RSSI: -60dBm | AP: TL-XAP1800GI-PoE-0002"
    }
  ]
}
```

**TP-Link 路由器字段映射**：

| 路由器原始字段 | 标准字段 | 转换规则 |
|--------------|---------|---------|
| `ip` | `asset_ip` | 直接映射 |
| `mac` | `mac_address` | `-` 替换为 `:` |
| `hostname` | `name` | `"anonymous"` → `null` |
| `type: "wired"` | `asset_type` | → `"server"` |
| `type: "wireless"` | `asset_type` | → `"client"` |
| `state: "online"` | `asset_status` | → `"online"` |
| - | `data_source` | 固定 `"tplink-router"` |
| - | `network_zone` | 固定 `"lan"` |
| `ssid` + `freq_name` + `rssi` + `ap_name` | `asset_description` | 组合描述字符串 |

#### 3.2.2 漏洞（Vulnerability）— Phase 2

```json
{
  "source": "wazuh",
  "data_type": "vulnerability",
  "items": [
    {
      "asset_ip": "192.168.0.30",
      "cve_id": "CVE-2024-1234",
      "title": "OpenSSH 远程代码执行漏洞",
      "severity": "high",
      "package_name": "openssh-server",
      "package_version": "8.9p1-3",
      "fix_available": true,
      "cvss_score": 7.8,
      "description": "...",
      "reference_url": "https://nvd.nist.gov/vuln/detail/CVE-2024-1234"
    }
  ]
}
```

#### 3.2.3 基线（Baseline）— Phase 3

```json
{
  "source": "wazuh-sca",
  "data_type": "baseline",
  "items": [
    {
      "asset_ip": "192.168.0.30",
      "check_id": "cis_ubuntu2204_1.1.1",
      "check_title": "确保 /tmp 分区已单独挂载",
      "status": "pass",
      "severity": "medium",
      "standard": "CIS Ubuntu 22.04",
      "remediation": "编辑 /etc/fstab 添加 /tmp 分区挂载项"
    }
  ]
}
```

#### 3.2.4 端口（Port）— Phase 4

```json
{
  "source": "nmap",
  "data_type": "port",
  "items": [
    {
      "asset_ip": "192.168.0.30",
      "port": 22,
      "protocol": "tcp",
      "state": "open",
      "service": "ssh",
      "version": "OpenSSH 8.9p1",
      "service_banner": "SSH-2.0-OpenSSH_8.9p1 Ubuntu-3"
    }
  ]
}
```

---

## 4. AI-miniSOC 侧改动

### 4.1 通用数据同步 API

#### 端点

```
POST /api/v1/data/sync
```

#### 请求体

```python
class DataSyncRequest(BaseModel):
    """通用数据同步请求"""
    source: str = Field(
        ...,
        description="数据来源标识: tplink-router / wazuh / nmap / openvas"
    )
    data_type: str = Field(
        ...,
        description="数据类型: asset / vulnerability / baseline / port"
    )
    items: list[dict] = Field(
        ...,
        description="数据列表，格式见各类型定义"
    )
    metadata: dict | None = Field(
        default=None,
        description="可选元信息: 采集耗时、条数等"
    )
```

#### 响应体

```python
class DataSyncResponse(BaseModel):
    """通用数据同步响应"""
    message: str
    data_type: str
    source: str
    total: int           # 接收到的条数
    created: int         # 新增
    updated: int         # 更新
    skipped: int         # 跳过（数据未变化）
    failed: int          # 失败
    errors: list[str]    # 失败详情（如有）
```

#### 处理流程

```python
# app/api/data_sync.py

@router.post("/data/sync")
async def sync_data(
    request: DataSyncRequest,
    db: Session = Depends(get_db),
    _auth: None = Depends(require_api_key),  # API Key 认证
):
    handler = SYNC_HANDLERS.get(request.data_type)
    if not handler:
        raise HTTPException(400, f"不支持的数据类型: {request.data_type}")

    result = handler.handle(request.source, request.items, db)
    return DataSyncResponse(
        message="同步完成",
        data_type=request.data_type,
        source=request.source,
        **result,
    )

# 处理器注册表
SYNC_HANDLERS = {
    "asset":          AssetSyncHandler(),
    "vulnerability":  VulnerabilitySyncHandler(),
    "baseline":       BaselineSyncHandler(),
    "port":           PortSyncHandler(),
}
```

### 4.2 API Key 服务间认证

新增一种认证方式，区别于普通用户的 JWT Token：

```python
# app/api/deps.py 新增

from app.core.config import settings

async def require_api_key(x_api_key: str = Header(...)):
    """Collector 服务间认证"""
    valid_keys = settings.COLLECTOR_API_KEYS  # 从环境变量/数据库读取
    if x_api_key not in valid_keys:
        raise HTTPException(status_code=401, detail="无效的 API Key")
    return x_api_key
```

```python
# app/core/config.py 新增

class Settings:
    # ...
    COLLECTOR_API_KEYS: list[str] = []  # 从环境变量读取，逗号分隔
```

```bash
# .env
COLLECTOR_API_KEYS=sk-minisoc-tplink-xxxxx,sk-minisoc-wazuh-yyyyy
```

### 4.3 数据库模型扩展

#### 新增 `soc_vulnerabilities` 表（Phase 2）

```sql
CREATE TABLE soc_vulnerabilities (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id        UUID REFERENCES soc_assets(id) ON DELETE CASCADE,
    asset_ip        TEXT NOT NULL,
    cve_id          TEXT,                              -- CVE-2024-1234
    title           TEXT,
    severity        VARCHAR(20) DEFAULT 'unknown',     -- critical/high/medium/low/unknown
    package_name    TEXT,
    package_version TEXT,
    fix_available   BOOLEAN DEFAULT FALSE,
    cvss_score      DECIMAL(3,1),
    description     TEXT,
    reference_url   TEXT,
    source          VARCHAR(50),                        -- wazuh / openvas / nmap
    detected_at     TIMESTAMP DEFAULT NOW(),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

#### 新增 `soc_baselines` 表（Phase 3）

```sql
CREATE TABLE soc_baselines (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id        UUID REFERENCES soc_assets(id) ON DELETE CASCADE,
    asset_ip        TEXT NOT NULL,
    check_id        TEXT,                              -- cis_ubuntu2204_1.1.1
    check_title     TEXT,
    status          VARCHAR(20),                       -- pass / fail / not_applicable / error
    severity        VARCHAR(20) DEFAULT 'info',
    standard        VARCHAR(100),                      -- CIS / 等保2.0 / 自定义
    remediation     TEXT,
    source          VARCHAR(50),                        -- wazuh-sca / tplink-router
    checked_at      TIMESTAMP DEFAULT NOW(),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

#### 现有表字段扩展

```sql
-- soc_assets.data_source 支持更多值
COMMENT ON COLUMN soc_assets.data_source IS
  '数据来源: manual / wazuh / tplink-router / nmap / openvas / cloud';

-- soc_asset_ports 新增 source 字段（Phase 4）
ALTER TABLE soc_asset_ports ADD COLUMN IF NOT EXISTS source VARCHAR(50) DEFAULT 'manual';
```

### 4.4 Handler 实现规范

每个 Handler 遵循统一接口：

```python
# app/services/sync_handlers/base.py

from abc import ABC, abstractmethod

class BaseSyncHandler(ABC):
    """同步处理器基类"""

    @abstractmethod
    def handle(self, source: str, items: list[dict], db: Session) -> dict:
        """
        处理同步数据

        返回: {
            "total": int,
            "created": int,
            "updated": int,
            "skipped": int,
            "failed": int,
            "errors": list[str]
        }
        """
        ...

# app/services/sync_handlers/asset_sync_handler.py

class AssetSyncHandler(BaseSyncHandler):
    """资产同步处理器"""

    def handle(self, source: str, items: list[dict], db: Session) -> dict:
        stats = {
            "total": len(items), "created": 0, "updated": 0,
            "skipped": 0, "failed": 0, "errors": [],
        }

        for item in items:
            try:
                # 按 IP + network_segment 查重
                existing = db.query(Asset).filter(
                    Asset.asset_ip == item["asset_ip"],
                    Asset.network_segment == item.get("network_segment", "default"),
                ).first()

                if existing:
                    # 增量对比：只更新有变化的字段
                    changed = self._diff_and_update(existing, item, source, db)
                    if changed:
                        stats["updated"] += 1
                    else:
                        stats["skipped"] += 1
                else:
                    # 新增资产
                    asset = Asset(**item)
                    db.add(asset)
                    stats["created"] += 1

            except Exception as e:
                stats["failed"] += 1
                stats["errors"].append(f"{item.get('asset_ip', '?')}: {str(e)}")

        db.commit()
        return stats
```

### 4.5 改动汇总

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `app/api/data_sync.py` | 🆕 新增 | 通用数据同步 API |
| `app/api/deps.py` | 修改 | 新增 `require_api_key` 依赖 |
| `app/core/config.py` | 修改 | 新增 `COLLECTOR_API_KEYS` 配置 |
| `app/services/sync_handlers/base.py` | 🆕 新增 | Handler 基类 |
| `app/services/sync_handlers/asset_sync_handler.py` | 🆕 新增 | 资产同步处理器 |
| `app/models/vulnerability.py` | 🆕 新增（Phase 2） | 漏洞数据模型 |
| `app/models/baseline.py` | 🆕 新增（Phase 3） | 基线数据模型 |
| `app/schemas/data_sync.py` | 🆕 新增 | 同步请求/响应 Schema |
| `main.py` | 修改 | 注册 data_sync 路由 |

---

## 5. Collector 框架设计

### 5.1 项目结构

```
src/collectors/
│
├── base/                              # 共享框架包
│   ├── pyproject.toml                 # pip install -e .
│   └── collector_framework/
│       ├── __init__.py
│       ├── base.py                    # BaseCollector + DataType
│       ├── sync_client.py             # AI-miniSOC API 客户端
│       ├── config.py                  # 配置管理
│       └── logging.py                 # 日志格式
│
├── tplink/                            # TP-Link Collector
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── config.example.yaml
│   └── tplink_collector/
│       ├── __init__.py
│       ├── __main__.py                # python -m tplink_collector
│       ├── collector.py               # 实现 BaseCollector
│       └── client.py                  # TP-Link SLP API 客户端
│
├── wazuh/                             # Wazuh Collector (Phase 2)
│   ├── Dockerfile
│   └── wazuh_collector/
│       └── ...
│
├── nmap/                              # Nmap Collector (Phase 4)
│   └── ...
│
├── docker-compose.yaml                # 统一编排
├── .env.example                       # 环境变量模板
└── README.md
```

### 5.2 共享框架 `collector-framework`

#### `base.py` — 采集器基类

```python
from abc import ABC, abstractmethod
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime

class DataType(Enum):
    """支持的数据类型"""
    ASSET = "asset"
    VULNERABILITY = "vulnerability"
    BASELINE = "baseline"
    PORT = "port"

@dataclass
class CollectResult:
    """单次采集结果"""
    source: str                          # 数据来源标识
    data_type: DataType                  # 数据类型
    items: list[dict]                    # 标准格式的数据列表
    collected_at: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)
    # metadata 可包含: duration_ms, raw_count, filtered_count 等

class BaseCollector(ABC):
    """
    采集器抽象基类

    每个 Collector 必须实现:
    - collect(): 执行采集，返回 CollectResult
    - test_connection(): 测试数据源连通性
    """

    source_name: str                     # 如 "tplink-router"
    supported_types: list[DataType]      # 该 Collector 支持的数据类型

    @abstractmethod
    async def collect(self, data_type: DataType) -> CollectResult:
        """
        执行采集

        Args:
            data_type: 要采集的数据类型

        Returns:
            CollectResult: 采集结果

        Raises:
            ValueError: 不支持的数据类型
            ConnectionError: 数据源不可达
        """
        ...

    @abstractmethod
    async def test_connection(self) -> bool:
        """测试与数据源的连通性"""
        ...

    def supports(self, data_type: DataType) -> bool:
        return data_type in self.supported_types
```

#### `sync_client.py` — AI-miniSOC API 客户端

```python
import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class MiniSOCClient:
    """
    AI-miniSOC 数据同步客户端

    负责:
    - 推送采集数据到 AI-miniSOC
    - 健康检查
    - 重试和错误处理
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: int = 30,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            headers={
                "X-API-Key": api_key,
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
        self.max_retries = max_retries

    async def sync(
        self,
        source: str,
        data_type: str,
        items: list[dict],
        metadata: Optional[dict] = None,
    ) -> dict:
        """
        推送采集数据到 AI-miniSOC

        Returns:
            {"message": "...", "total": N, "created": N, "updated": N, ...}
        """
        payload = {
            "source": source,
            "data_type": data_type,
            "items": items,
        }
        if metadata:
            payload["metadata"] = metadata

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                resp = await self.client.post(
                    f"{self.base_url}/api/v1/data/sync",
                    json=payload,
                )
                resp.raise_for_status()
                result = resp.json()
                logger.info(
                    f"同步成功: source={source}, type={data_type}, "
                    f"total={result.get('total')}, created={result.get('created')}, "
                    f"updated={result.get('updated')}, failed={result.get('failed')}"
                )
                return result
            except httpx.HTTPStatusError as e:
                last_error = e
                logger.warning(
                    f"同步失败 (attempt {attempt}/{self.max_retries}): "
                    f"status={e.response.status_code}, body={e.response.text}"
                )
            except httpx.RequestError as e:
                last_error = e
                logger.warning(f"网络错误 (attempt {attempt}/{self.max_retries}): {e}")

            if attempt < self.max_retries:
                import asyncio
                await asyncio.sleep(2 ** attempt)  # 指数退避

        raise RuntimeError(f"同步失败，重试 {self.max_retries} 次后放弃: {last_error}")

    async def health_check(self) -> bool:
        """检查 AI-miniSOC 是否可达"""
        try:
            resp = await self.client.get(f"{self.base_url}/api/v1/health")
            return resp.status_code == 200
        except Exception:
            return False

    async def close(self):
        await self.client.aclose()
```

#### `config.py` — 配置管理

```python
from dataclasses import dataclass, field
from typing import Optional
import yaml
import os

@dataclass
class CollectorConfig:
    """Collector 通用配置"""

    # AI-miniSOC 连接
    minisoc_url: str = ""
    minisoc_api_key: str = ""

    # 采集调度
    interval: int = 300                   # 采集间隔（秒）
    collect_types: Optional[list[str]] = None  # 要采集的数据类型，None = 全部

    # 运行模式
    once: bool = False                    # 单次执行后退出

    # 数据源特定配置（由各 Collector 自行解析）
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str) -> "CollectorConfig":
        with open(path) as f:
            cfg = yaml.safe_load(f) or {}

        minisoc_cfg = cfg.get("minisoc", {})
        collect_cfg = cfg.get("collect", {})

        return cls(
            minisoc_url=os.getenv("MINISOC_URL", minisoc_cfg.get("url", "")),
            minisoc_api_key=os.getenv("MINISOC_API_KEY", minisoc_cfg.get("api_key", "")),
            interval=int(os.getenv("COLLECT_INTERVAL", collect_cfg.get("interval", 300))),
            collect_types=collect_cfg.get("types"),
            once=collect_cfg.get("once", False),
            extra=cfg,  # 保留完整配置供子类使用
        )
```

### 5.3 Collector 通用运行模式

每个 Collector 的 `__main__.py` 遵循统一模式：

```python
# tplink_collector/__main__.py

import asyncio
import argparse
import signal
import sys
import os
import logging
from collector_framework.config import CollectorConfig
from collector_framework.sync_client import MiniSOCClient
from collector_framework.base import DataType
from tplink_collector.collector import TPLinkCollector

logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="TP-Link 路由器数据采集器")
    parser.add_argument("--config", default="config.yaml", help="配置文件路径")
    parser.add_argument("--once", action="store_true", help="单次执行")
    parser.add_argument("--test", action="store_true", help="测试连通性")
    parser.add_argument("--interval", type=int, help="覆盖采集间隔（秒）")
    args = parser.parse_args()

    # 加载配置
    config = CollectorConfig.from_yaml(args.config)
    if args.once:
        config.once = True
    if args.interval:
        config.interval = args.interval

    # 初始化 Collector
    router_cfg = config.extra.get("router", {})
    collector = TPLinkCollector(
        host=os.getenv("ROUTER_HOST", router_cfg.get("host", "192.168.0.1")),
        username=os.getenv("ROUTER_USERNAME", router_cfg.get("username", "")),
        password=os.getenv("ROUTER_PASSWORD", router_cfg.get("password", "")),
        port=int(os.getenv("ROUTER_PORT", router_cfg.get("port", 80))),
    )

    # 初始化 AI-miniSOC 客户端
    soc_client = MiniSOCClient(
        base_url=config.minisoc_url,
        api_key=config.minisoc_api_key,
    )

    # 测试模式
    if args.test:
        ok_router = asyncio.run(collector.test_connection())
        ok_soc = asyncio.run(soc_client.health_check())
        print(f"路由器连通性: {'OK' if ok_router else 'FAIL'}")
        print(f"AI-miniSOC 连通性: {'OK' if ok_soc else 'FAIL'}")
        sys.exit(0 if (ok_router and ok_soc) else 1)

    # 运行模式
    async def run_once():
        logger.info("开始采集...")
        result = await collector.collect(DataType.ASSET)
        logger.info(f"采集完成: {len(result.items)} 条")
        sync_result = await soc_client.sync(
            source=result.source,
            data_type=result.data_type.value,
            items=result.items,
            metadata=result.metadata,
        )
        logger.info(f"同步结果: {sync_result}")

    if config.once:
        asyncio.run(run_once())
    else:
        shutdown = asyncio.Event()

        def _signal_handler(*_):
            shutdown.set()

        signal.signal(signal.SIGTERM, _signal_handler)
        signal.signal(signal.SIGINT, _signal_handler)

        async def loop():
            while not shutdown.is_set():
                try:
                    await run_once()
                except Exception as e:
                    logger.error(f"采集失败: {e}", exc_info=True)
                try:
                    await asyncio.wait_for(shutdown.wait(), timeout=config.interval)
                except asyncio.TimeoutError:
                    pass  # 正常超时，继续下一轮

        logger.info(f"启动定时采集，间隔 {config.interval}s")
        asyncio.run(loop())

    asyncio.run(soc_client.close())

if __name__ == "__main__":
    main()
```

---

## 6. TP-Link Collector 详细设计

### 6.1 TP-Link SLP API 客户端

> 详细的 API 逆向分析见 [2026-06-07-tplink-router-integration.md](2026-06-07-tplink-router-integration.md)

```python
# tplink_collector/client.py

import httpx
import logging
from typing import Optional
from urllib.parse import unquote

logger = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """认证失败"""
    pass


class APIError(Exception):
    """API 调用失败"""
    pass


class TPLinkSLPClient:
    """
    TP-Link SLP 路由器 API 客户端

    适用于 TL-R479GP-AC 等使用 SLP (Single Page Application) 管理界面的 TP-Link 路由器。
    通过逆向分析 Web 管理界面获得 API 接口。

    认证流程:
      1. 密码经 XOR 字符映射混淆 (securityEncode) 加密
      2. POST / 发送登录请求，获取 stok (会话令牌)
      3. 后续请求使用 /stok=<token>/ds 端点
      4. 必须携带 X-Requested-With: XMLHttpRequest 请求头
    """

    XOR_KEY1 = "RDpbLfCPsJZ7fiv"
    XOR_KEY2 = (
        "yLwVl0zKqws7LgKPRQ84Mdt708T1qQ3Ha7xv3H7NyU84p21BriUWBU43odz3iP4r"
        "BL3cD02KZciXTysVXiV8ngg6vL48rPJyAUw0HurW20xqxv9aYb4M9wK1Ae0wlro5"
        "10qXeU07kV57fQMc8L6aLgMLwygtc0F10a0Dg70TOoouyFhdysuRMO51yY5ZlOZZL"
        "Eal1h0t9YQW0Ko7oBwmCAHoic4HYbUyVeU3sfQ1xtXcPcf1aT303wAQhv66qzW"
    )

    API_HEADERS = {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
    }

    def __init__(self, host: str, username: str, password: str, port: int = 80):
        self.base_url = f"http://{host}:{port}"
        self.username = username
        self.password = password
        self.client = httpx.AsyncClient(timeout=30, verify=False)
        self.stok: Optional[str] = None

    @classmethod
    def security_encode(cls, password: str) -> str:
        """
        TP-Link SLP 密码 XOR 混淆加密

        算法:
          对 password 和 key1 逐字符 XOR，
          结果对 key2 长度取模，映射到 key2 字符。

        超出长度部分用 187 做 XOR 基准值。
        """
        result = ""
        k1, k2 = cls.XOR_KEY1, cls.XOR_KEY2
        pwd_len, k1_len, k2_len = len(password), len(k1), len(k2)
        length = max(pwd_len, k1_len)
        for i in range(length):
            char_pwd = char_key = 187
            if i >= pwd_len:
                char_key = ord(k1[i])
            elif i >= k1_len:
                char_pwd = ord(password[i])
            else:
                char_pwd = ord(password[i])
                char_key = ord(k1[i])
            result += k2[(char_pwd ^ char_key) % k2_len]
        return result

    async def login(self) -> str:
        """
        登录路由器，获取 stok token

        Returns:
            stok: 32位十六进制会话令牌

        Raises:
            ConnectionError: 路由器不可达
            AuthenticationError: 用户名或密码错误
        """
        enc_pwd = self.security_encode(self.password)
        resp = await self.client.post(
            f"{self.base_url}/",
            json={
                "method": "do",
                "login": {
                    "username": self.username,
                    "password": enc_pwd,
                },
            },
        )

        if resp.status_code == 401:
            data = resp.json()
            raise AuthenticationError(
                f"登录失败: code={data.get('error_code')}, "
                f"剩余尝试={data.get('data', {}).get('time', '?')}"
            )

        resp.raise_for_status()
        data = resp.json()

        if data.get("error_code") != 0:
            raise AuthenticationError(f"登录失败: {data}")

        self.stok = data["stok"]
        logger.info(f"登录成功，获取 stok: {self.stok[:8]}...")
        return self.stok

    async def get_hosts(self) -> list[dict]:
        """
        获取在线终端设备列表

        Returns:
            设备列表，每个设备为标准化的字典
        """
        if not self.stok:
            await self.login()

        url = f"{self.base_url}/stok={self.stok}/ds"
        resp = await self.client.post(
            url,
            json={"method": "get", "host_management": {"table": "host_info"}},
            headers=self.API_HEADERS,
        )

        if resp.status_code == 401:
            # stok 过期，重新登录
            self.stok = None
            return await self.get_hosts()

        resp.raise_for_status()
        data = resp.json()

        if data.get("error_code") != 0:
            raise APIError(f"获取设备列表失败: {data}")

        # 解析嵌套结构
        hosts = []
        for item in data["host_management"]["host_info"]:
            for key, host_data in item.items():
                hosts.append(self._normalize_host(host_data))

        logger.info(f"获取到 {len(hosts)} 台在线设备")
        return hosts

    async def get_system_info(self) -> dict:
        """获取路由器系统信息（可用于基线检查）"""
        if not self.stok:
            await self.login()

        url = f"{self.base_url}/stok={self.stok}/ds"
        resp = await self.client.post(
            url,
            json={"method": "get", "system": {"info": None}},
            headers=self.API_HEADERS,
        )
        resp.raise_for_status()
        return resp.json()

    async def logout(self):
        """退出登录，释放 stok"""
        if self.stok:
            try:
                url = f"{self.base_url}/stok={self.stok}/ds"
                await self.client.post(
                    url,
                    json={"method": "do", "system": {"logout": None}},
                    headers=self.API_HEADERS,
                )
            except Exception as e:
                logger.debug(f"注销时出错（可忽略）: {e}")
            finally:
                self.stok = None

    def _normalize_host(self, raw: dict) -> dict:
        """
        将路由器原始数据转换为 AI-miniSOC 标准格式

        原始字段 → 标准字段:
        - ip → asset_ip
        - mac → mac_address (- 替换为 :)
        - hostname → name (anonymous → null)
        - type → asset_type (wired→server, wireless→client)
        - state → asset_status
        - ssid/freq_name/rssi/ap_name → asset_description
        """
        mac = raw.get("mac", "")
        hostname = raw.get("hostname", "")
        conn_type = raw.get("type", "")
        state = raw.get("state", "")

        # 构建描述信息
        desc_parts = []
        if conn_type == "wireless":
            desc_parts.append("无线设备")
            if raw.get("ssid"):
                desc_parts.append(f"SSID: {raw['ssid']}")
            if raw.get("freq_name"):
                desc_parts.append(raw["freq_name"])
            if raw.get("rssi"):
                desc_parts.append(f"RSSI: {raw['rssi']}dBm")
            if raw.get("ap_name"):
                desc_parts.append(f"AP: {raw['ap_name']}")
        elif conn_type == "wired":
            desc_parts.append("有线设备")

        # 流量信息
        down_speed = int(raw.get("down_speed", "0"))
        up_speed = int(raw.get("up_speed", "0"))
        if down_speed or up_speed:
            desc_parts.append(f"↑{up_speed}Kbps ↓{down_speed}Kbps")

        # 连接时间
        connect_date = unquote(raw.get("connect_date", ""))
        connect_time = unquote(raw.get("connect_time", ""))
        if connect_date and connect_time:
            desc_parts.append(f"接入: {connect_date} {connect_time}")

        return {
            "name": hostname if hostname != "anonymous" else None,
            "asset_ip": raw.get("ip"),
            "mac_address": mac.replace("-", ":") if mac else None,
            "asset_type": "server" if conn_type == "wired" else "client",
            "asset_status": state,
            "network_zone": "lan",
            "network_segment": "default",
            "criticality": "normal",
            "data_source": "tplink-router",
            "asset_description": " | ".join(desc_parts) if desc_parts else None,
        }

    async def close(self):
        await self.client.aclose()
```

### 6.2 Collector 实现

```python
# tplink_collector/collector.py

from collector_framework.base import BaseCollector, DataType, CollectResult
from tplink_collector.client import TPLinkSLPClient
import logging

logger = logging.getLogger(__name__)


class TPLinkCollector(BaseCollector):
    """TP-Link 路由器数据采集器"""

    source_name = "tplink-router"
    supported_types = [DataType.ASSET]  # Phase 1 只做资产

    def __init__(self, host: str, username: str, password: str, port: int = 80):
        self.client = TPLinkSLPClient(host, username, password, port)

    async def collect(self, data_type: DataType) -> CollectResult:
        if data_type == DataType.ASSET:
            return await self._collect_assets()
        raise ValueError(f"不支持的数据类型: {data_type}")

    async def _collect_assets(self) -> CollectResult:
        """采集在线终端设备列表"""
        await self.client.login()
        try:
            hosts = await self.client.get_hosts()
            return CollectResult(
                source=self.source_name,
                data_type=DataType.ASSET,
                items=hosts,
                metadata={"host_count": len(hosts)},
            )
        finally:
            await self.client.logout()

    async def test_connection(self) -> bool:
        """测试路由器连通性"""
        try:
            await self.client.login()
            await self.client.logout()
            return True
        except Exception as e:
            logger.error(f"路由器连通性测试失败: {e}")
            return False
```

### 6.3 配置文件

```yaml
# tplink/config.example.yaml

# AI-miniSOC 连接配置
minisoc:
  url: http://host.docker.internal:8000
  # api_key 建议通过环境变量 MINISOC_API_KEY 注入

# 路由器连接配置
router:
  host: 192.168.0.1               # 也可以通过环境变量 ROUTER_HOST 覆盖
  port: 80
  username: tploginadmin          # 也可以通过环境变量 ROUTER_USERNAME 覆盖
  # password 必须通过环境变量 ROUTER_PASSWORD 注入

# 采集调度
collect:
  types:
    - asset                       # Phase 1 只采集资产
    # - baseline                  # Phase 3 启用基线
  interval: 300                   # 5 分钟
  once: false                     # true = 单次执行后退出
```

---

## 7. Docker 部署

### 7.1 Dockerfile

```dockerfile
# tplink/Dockerfile

# ---- 构建阶段 ----
FROM python:3.14-slim AS builder

WORKDIR /build

# 安装共享框架
COPY base/ /build/base/
RUN pip install --no-cache-dir /build/base

# 安装 Collector
COPY tplink/ /build/tplink/
RUN pip install --no-cache-dir /build/tplink

# ---- 运行阶段 ----
FROM python:3.14-slim

WORKDIR /app

# 从 builder 复制已安装的包
COPY --from=builder /usr/local/lib/python3.14/site-packages/ \
    /usr/local/lib/python3.14/site-packages/
COPY --from=builder /usr/local/bin/ /usr/local/bin/

# 复制默认配置
COPY tplink/config.example.yaml /app/config.yaml

# 健康检查
HEALTHCHECK --interval=60s --timeout=5s --retries=3 \
    CMD python -m tplink_collector --test || exit 1

ENTRYPOINT ["python", "-m", "tplink_collector"]
CMD ["--config", "/app/config.yaml"]
```

### 7.2 docker-compose 编排

```yaml
# src/collectors/docker-compose.yaml
version: "3.8"

services:
  # ═══════════════════════════════════════════
  #  TP-Link 路由器采集器
  # ═══════════════════════════════════════════
  tplink-collector:
    build:
      context: .
      dockerfile: tplink/Dockerfile
    container_name: minisoc-tplink-collector
    restart: unless-stopped
    environment:
      - MINISOC_URL=${MINISOC_URL:-http://host.docker.internal:8000}
      - MINISOC_API_KEY=${MINISOC_API_KEY}
      - ROUTER_HOST=${ROUTER_HOST:-192.168.0.1}
      - ROUTER_USERNAME=${ROUTER_USERNAME:-tploginadmin}
      - ROUTER_PASSWORD=${ROUTER_PASSWORD}
      - COLLECT_INTERVAL=${TPLINK_INTERVAL:-300}
    mem_limit: 128m
    cpus: 0.5
    networks:
      - minisoc-net
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  # ═══════════════════════════════════════════
  #  Wazuh 采集器 (Phase 2)
  # ═══════════════════════════════════════════
  # wazuh-collector:
  #   build:
  #     context: .
  #     dockerfile: wazuh/Dockerfile
  #   container_name: minisoc-wazuh-collector
  #   restart: unless-stopped
  #   environment:
  #     - MINISOC_URL=${MINISOC_URL:-http://host.docker.internal:8000}
  #     - MINISOC_API_KEY=${MINISOC_API_KEY}
  #     - WAZUH_HOST=${WAZUH_HOST:-192.168.0.30}
  #     - WAZUH_PORT=${WAZUH_PORT:-55000}
  #     - WAZUH_USERNAME=${WAZUH_USERNAME:-wazuh-wui}
  #     - WAZUH_PASSWORD=${WAZUH_PASSWORD}
  #     - COLLECT_INTERVAL=${WAZUH_INTERVAL:-600}
  #   mem_limit: 256m
  #   cpus: 0.5
  #   networks:
  #     - minisoc-net

networks:
  minisoc-net:
    driver: bridge
```

### 7.3 环境变量模板

```bash
# src/collectors/.env.example

# ─── 通用 ───
MINISOC_URL=http://host.docker.internal:8000
MINISOC_API_KEY=sk-minisoc-xxxxx

# ─── TP-Link Collector ───
ROUTER_HOST=192.168.0.1
ROUTER_USERNAME=tploginadmin
ROUTER_PASSWORD=your-router-password
TPLINK_INTERVAL=300

# ─── Wazuh Collector (Phase 2) ───
# WAZUH_HOST=192.168.0.30
# WAZUH_PORT=55000
# WAZUH_USERNAME=wazuh-wui
# WAZUH_PASSWORD=your-wazuh-password
# WAZUH_INTERVAL=600
```

### 7.4 常用运维命令

```bash
# 构建并启动
docker compose up -d tplink-collector

# 查看日志
docker compose logs -f tplink-collector

# 单次执行
docker compose run --rm tplink-collector python -m tplink_collector --once

# 测试连通性
docker compose run --rm tplink-collector python -m tplink_collector --test

# 重启
docker compose restart tplink-collector

# 停止
docker compose down tplink-collector
```

---

## 8. 分阶段实施计划

### Phase 1: TP-Link 资产采集（建议 3-5 天）

**目标**：跑通 "Collector 采集 → API 同步 → 前端展示" 完整链路

| 步骤 | 工作内容 | 产出 |
|------|---------|------|
| 1.1 | AI-miniSOC 新增 `POST /api/v1/data/sync` 通用同步 API | `app/api/data_sync.py` |
| 1.2 | AI-miniSOC 新增 `require_api_key` 认证 | `app/api/deps.py` 修改 |
| 1.3 | AI-miniSOC 实现 `AssetSyncHandler` | `app/services/sync_handlers/asset_sync_handler.py` |
| 1.4 | 开发 `collector-framework` 共享框架 | `src/collectors/base/` |
| 1.5 | 开发 `tplink-collector` | `src/collectors/tplink/` |
| 1.6 | Docker 化 + 端到端测试 | `docker-compose.yaml` |
| 1.7 | 前端资产列表增加"数据源"筛选 | 前端小改 |

**验证标准**：
- [ ] `docker compose up tplink-collector` 启动后，5分钟内 AI-miniSOC 资产表出现路由器设备
- [ ] 前端资产列表能看到来源为 `tplink-router` 的资产
- [ ] 连续运行24小时无崩溃

### Phase 2: Wazuh 漏洞采集（建议 1-2 周）

| 步骤 | 工作内容 |
|------|---------|
| 2.1 | 新增 `soc_vulnerabilities` 表 |
| 2.2 | 实现 `VulnerabilitySyncHandler` |
| 2.3 | 开发 `wazuh-collector`（资产 + 漏洞） |
| 2.4 | 前端漏洞管理页面 |
| 2.5 | 前端资产详情页漏洞 Tab 激活 |

### Phase 3: 基线采集（建议 1 周）

| 步骤 | 工作内容 |
|------|---------|
| 3.1 | 新增 `soc_baselines` 表 |
| 3.2 | 实现 `BaselineSyncHandler` |
| 3.3 | Wazuh SCA 基线采集 |
| 3.4 | TP-Link 路由器安全配置基线采集 |
| 3.5 | 前端基线管理页面 |

### Phase 4: 端口采集 + 更多数据源（持续扩展）

| 步骤 | 工作内容 |
|------|---------|
| 4.1 | 实现 `PortSyncHandler` |
| 4.2 | 开发 `nmap-collector` |
| 4.3 | 资产详情页端口 Tab 数据源展示 |

---

## 9. 注意事项

### 9.1 安全

| 事项 | 说明 |
|------|------|
| **API Key 保护** | 通过环境变量注入，不写入代码或配置文件 |
| **路由器密码** | 仅存在于 Collector 容器环境变量中，不经过 AI-miniSOC |
| **stok 是临时令牌** | 每次登录获取，用完即注销，不持久化 |
| **只读操作** | Phase 1 的 TP-Link Collector 只使用 `method: "get"`，不修改路由器配置 |
| **网络安全** | Collector 与 AI-miniSOC 通过 Docker 内部网络通信，不暴露端口 |

### 9.2 可靠性

| 事项 | 说明 |
|------|------|
| **stok 过期处理** | Client 内部自动检测 401 并重新登录 |
| **指数退避重试** | MiniSOCClient 内置 3 次重试 + 指数退避 |
| **优雅关闭** | 监听 SIGTERM/SIGINT，完成当前采集后退出 |
| **资源限制** | 每个 Collector 限制内存 128-256MB，CPU 0.5 核 |
| **日志轮转** | Docker json-file 日志限制 10MB × 3 文件 |

### 9.3 TP-Link 路由器特有限制

| 限制 | 应对策略 |
|------|---------|
| 同时只允许一个管理员登录 | Collector 每次操作后立即 logout，不长期占用 |
| 无正式 API 文档 | 基于 SLP 界面逆向分析，固件更新可能导致 API 变化 |
| host_info 只返回在线设备 | 离线设备由 AI-miniSOC 侧通过"N次未出现"逻辑标记 |
| 请求频率限制 | 同步间隔不低于 1 分钟，建议 5 分钟 |

---

## 10. 变更记录

| 日期 | 版本 | 说明 |
|------|------|------|
| 2026-06-07 | v1.0 | 架构设计文档初始版本 |
