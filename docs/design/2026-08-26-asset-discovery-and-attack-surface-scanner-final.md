# 资产发现与攻击面扫描采集器 — 设计方案（最终稿）

| 项目 | 内容 |
|---|---|
| 文档版本 | final（整合 v1.0 初稿 + v1.1 修订 + v1.2 架构补丁 + v1.3 评审修复，单一权威稿） |
| 编写日期 | 2026-08-26 |
| 状态 | 最终稿（已吸收全部评审：独立代码级评审 + 控制面原型评审 + v1.3 修复补丁） |
| 关联 PRD | P3 / F1.3（资产对账源头补齐）、F4.2（推送场景 4 影子资产）、F1.1（暴露面风险评分）、F3.2（生命周期） |
| 部署背景 | 拟将扫描采集器部署于 192.168.0.45（Kali Linux），支持多扫描器、从 AI-miniSOC 下发任务、在线检测 |
| 目标读者 | 后端 / 采集器 / 前端 / 运维 / 架构评审 |
| 配套产出 | [控制面原型](./2026-08-26-control-plane-prototype.html)（交互式）、[部署架构图](./2026-08-26-deployment-architecture.svg) |

> **本文档演进**：v1.0 初稿 → v1.1（修复「发现/台账解耦、表名冲突、Alembic 路径」三处硬伤）→ v1.2（控制面/数据面分离 + 拉模型 + 三层在线检测）→ v1.3 评审修复补丁（F-1~F-3 必修、O-1~O-5 优化、M-1~M-3 瑕疵）。过程稿已合并入本最终稿并删除。

---

## 一、背景与目标

### 1.1 现状缺口

当前 AI-miniSOC 的资产数据源是被动的：

| 数据源 | 看见什么 | 看不见什么 |
|---|---|---|
| **tplink-collector** | 路由器 DHCP 客户端表 | 未接路由器/DHCP 已过的设备；公网暴露面 |
| **wazuh-collector** | 已装 agent 的主机 | 未装 agent 的设备（含服务器、IoT） |

由此产生两个**结构性缺口**：

1. **影子资产**：内网存在但未被纳管的设备，`soc_assets` 里完全没有记录
2. **暴露面失明**：公网开放端口/服务无人探查，风险评分缺数据

### 1.2 已有但未喂饱的能力（复用，不重复造）

| 已实现 | 等数据 |
|---|---|
| F1.3 资产对账 (`asset_reconciliation`) | shadow/offline/mismatch 差异**只能比对已有数据**；当前 shadow 仅来自 Wazuh（agent 有但台账无）。需扩展「发现维度」才能消费 scanner 源 |
| F1.1 风险评分 (`asset_risk.py`) | `ports_score` 维度依赖 `soc_asset_ports`，公网资产端口数据为 0 |
| F4.2 推送场景 4「影子资产发现」 | `_find_new_shadows` 已按 `TYPE_SHADOW + status='pending'` 过滤（**不要求 `asset_id=None`**）；消费 scanner 源 shadow 仅需 F1.3 能产出该行，并需补充 scanner 来源通知文案 |
| `/data/health` 三层聚合 | `scanner` 通道预留但无人接入 |
| **既有端口能力** | `app/api/asset_ports.py`(CRUD) + `schemas/asset_port.py` + MCP `list_asset_ports` 已存在；`PortSyncHandler` 是「采集→同步」管道，与既有「人工 CRUD/查询」互补，复用 `AssetPort` 模型**不重复定义** |

### 1.3 目标

新增一个**主动探测型采集器** `scanner-collector`，闭环以上缺口：

| 编号 | 功能 | 业务价值 |
|---|---|---|
| **F-S1** | **内网资产发现**：按 CIDR 主动 ping + 端口扫描，发现未纳管设备 | 为 F1.3 **新增的「发现维度」**提供数据源 → 对账产出 shadow → F4.2 推送（**需扩展 F1.3，非零改动**） |
| **F-S2** | **公网暴露面扫描**：对 `exposure_level="public"` 的资产做服务版本探测 | 喂饱 F1.1 风险评分、`soc_asset_ports.vulnerability`（vulnerability 由 Phase 4 NSE 填充，本期留空） |
| **F-S3** | **可观测性 + 治理**：扫描任务可查询、目标可管理、发现可纳管、全程审计、扫描器在线可检测 | 满足 X1 权限矩阵 + 合规可追溯 + 补掉 P4「采集中断无感知」缺口 |

> **关键变更（v1.1 起）**：F-S1 的产出**不再是 `soc_assets` 行**，而是独立的 `soc_scan_findings` 发现记录。台账写入仅发生在用户「一键纳管」时。扫描器调度与管理全部上提到 AI-miniSOC 控制面（v1.2 起），扫描器只做「心跳 + 拉任务 + 执行 + 回推」。

---

## 二、Why — 为什么必须升级为「控制面 + 数据面」

> 本节承接 v1.1（已解决发现/台账解耦）之上、v1.2 的范式升级论证，因用户三个诉求本质都是控制面诉求。

| 问题 | 现象（v1.1 内嵌调度假设下） | 后果 |
|---|---|---|
| **P-a 无中央任务视图** | 任务只存在于扫描器进程内存 | 多扫描器时，谁在扫、扫到哪、是否失败，AI-miniSOC 完全不知；UI 无法统一触发/取消/重试 |
| **P-b 无法下发任务** | 扫描器只按自身 cron 跑 | 用户「现在扫一下 192.168.0.55」无法满足；F1.3 shadow → 单 IP 重扫也卡在「scanner 需暴露 HTTP」 |
| **P-c 在线状态不可知** | 扫描器无注册/心跳（实测 `collectors/` 框架无 heartbeat/register，仅 `MiniSOCClient` 推数据） | 192.168.0.45 宕机无人知——与 P4「192.168.0.2 凌晨中断无感知」同一类缺口 |

**结论（单一事实源原则）**：所有扫描任务的创建、调度、编排、取消、重试、审计，都在 AI-miniSOC（控制面）。扫描器（数据面）仅保留「执行必需的轻量循环」——心跳、拉任务、跑 nmap、推结果、回写状态——**不含任何业务调度**。

---

## 三、非目标（Non-goals）

| # | 不做什么 | 理由 |
|---|---|---|
| NG-1 | 不在本期做扫描器侧「本地 cron 安全网」 | 拉模型下离线任务留 `pending`，恢复后自动认领，无需本地兜底 |
| NG-2 | 不做扫描器间 P2P / 级联 | 多扫描器由控制面统一编排，扫描器之间互不感知 |
| NG-3 | 不为扫描器引入独立数据库 | 扫描器无状态，状态全部在 AI-miniSOC |
| NG-4 | 不改造现有 tplink/wazuh-collector 为拉模型 | 仅 scanner-collector 采用新范式 |
| NG-5 | 不做扫描器自动发现/零配置接入 | 首次上线需运维在控制面「注册」（分配 scanner_id + API Key + 能力声明），避免未授权主机伪装扫描器 |

---

## 四、用户故事（User Stories）

| 编号 | 角色 | 故事 | 验收标准 |
|---|---|---|---|
| US-1 | 安全运维（operator） | 我希望在 AI-miniSOC 看到所有扫描器的在线/离线状态 | 仪表板实时显示 192.168.0.45 等扫描器最后心跳、当前状态、在跑任务数；离线 > 90s 自动标红并告警 |
| US-2 | 安全运维（operator） | 我希望临时对某个 IP/网段下发一次扫描 | 选「目标 + 模式 + 指定扫描器（或自动路由）」，任务立即 `pending`，目标扫描器下次轮询认领执行 |
| US-3 | 安全运维（operator） | 我希望多台扫描器按能力/子网各扫各的 | internal 任务按 CIDR 匹配 `reachable_subnets` 自动派发；public 任务派给声明 `public` 能力者 |
| US-4 | SOC 管理员（admin） | 我希望某台扫描器离线时自动收到通知 | 看门狗检测离线 → F4.2 类通知（站内 + 可选邮件），附 scanner_id/IP/最后心跳 |
| US-5 | 审计员（auditor） | 我希望每次扫描任务可追溯到「谁触发、哪台扫描器执行、扫了什么、耗时、结果」 | `soc_scanner_tasks` + `soc_audit_logs` 完整记录；scanner_id 回写任务行 |
| US-6 | 安全运维（operator） | 我希望扫描器执行中可取消 | 控制面 `POST /scan/tasks/{uuid}/cancel` → 扫描器下次轮询读到 `cancelled` 状态中止 nmap |

---

## 五、整体架构

### 5.1 架构总览（控制面 + 数据面 + 既有链路）

```
┌──────────────────────────────────────────────────────────────────────────┐
│  AI-miniSOC 控制面（192.168.0.102:8000，新增扫描调度域）                    │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │  scan_watchdog_scheduler（lifespan 起，每 60s）                      │  │
│  │    → now - last_heartbeat > 90s → 标 scanner offline + 告警          │  │
│  │    → running 超时(>6h) → 标 failed + 自动重派                        │  │
│  ├────────────────────────────────────────────────────────────────────┤  │
│  │  central_scan_scheduler（lifespan 起，固定秒数间隔对齐 03:00/04:00）  │  │
│  │    → 建任务（指定 scanner_id 或 auto 路由）→ soc_scanner_tasks       │  │
│  ├────────────────────────────────────────────────────────────────────┤  │
│  │  API /scan/agents/*   /scan/tasks/*   /scan/findings/*   /scan/run   │  │
│  ├────────────────────────────────────────────────────────────────────┤  │
│  │  表：soc_scanner_agents（注册/状态）  soc_scanner_tasks（任务）       │  │
│  │       soc_scan_targets  soc_scan_findings  soc_source_health          │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                              ▲  pull / heartbeat（出向）                    │
│                              │ 控制指令/任务/数据 全部经 HTTP                 │
└──────────────────────────────┬───────────────────────────────────────────┘
                                │ （扫描器只出向请求，天然穿透 NAT/防火墙）
        ┌───────────────────────┼───────────────────────┐
        ▼                       ▼                        ▼
┌──────────────────┐  ┌──────────────────┐   ┌──────────────────┐
│ 扫描器 A          │  │ 扫描器 B          │   │ 扫描器 C（可选）  │
│ 192.168.0.45 Kali │  │ 另一子网/机房     │   │ …                │
│ scanner-collector │  │ scanner-collector │   │ scanner-collector│
│  ┌──────────────┐ │  │  ┌──────────────┐ │   │  ┌──────────────┐ │
│  │ 轻量循环：    │ │  │  │ 轻量循环：    │ │   │  │ 轻量循环：    │ │
│  │ 1. heartbeat  │ │  │  │ 1. heartbeat  │ │   │  │ 1. heartbeat  │ │
│  │ 2. pull task  │ │  │  │ 2. pull task  │ │   │  │ 2. pull task  │ │
│  │ 3. run nmap   │ │  │  │ 3. run nmap   │ │   │  │ 3. run nmap   │ │
│  │ 4. push data  │ │  │  │ 4. push data  │ │   │  │ 4. push data  │ │
│  │ 5. report st. │ │  │  │ 5. report st. │ │   │  │ 5. report st. │ │
│  └──────────────┘ │  │  └──────────────┘ │   │  └──────────────┘ │
│ 无业务调度逻辑    │  │ 无业务调度逻辑    │   │ 无业务调度逻辑    │
└──────────────────┘  └──────────────────┘   └──────────────────┘

        scanner 推数据 ──POST /data/sync──▶ DiscoverySyncHandler → soc_scan_findings
                                          └─▶ PortSyncHandler     → soc_asset_ports
        soc_scan_findings ──F1.3 扩展发现维度──▶ TYPE_SHADOW(asset_id=None)
                                                    └─▶ F4.2 推送（scanner 文案） ──▶ 纳管写 soc_assets
```

### 5.2 与现有组件的关系

| 已有组件 | 接入方式 | 改动量 |
|---|---|---|
| **`BaseCollector`** (`collector_framework/base.py`) | 新写 `ScannerCollector` 实现 `collect()` / `test_connection()` | 仅新增 1 个文件 |
| **`MiniSOCClient`** (`collector_framework/sync_client.py`) | 直接 `await client.sync(source="scanner", ...)` | 0 改动（复用现有 X-API-Key 推送机制） |
| **`/api/v1/data/sync`** (`app/api/data_sync.py`) | 复用现有端点 + 新增 `DiscoverySyncHandler` / `PortSyncHandler` | 注册 2 个 handler |
| **`BaseSyncHandler`** | 新写 2 个 handler 复用 `_handle_one` 模式 | 2 个新文件 |
| **`soc_assets`** | **scanner 不直接写**；仅在用户「一键纳管」时由 API 创建 | 0 schema 改动 |
| **`soc_asset_ports`** | 复用现有表（模型已存在） | 0 schema 改动 |
| **`soc_source_health`** | 自动接入 `_SOURCE_HEALTH_KEYS` | 2 行注册 |
| **`soc_audit_logs`** | 复用 `create_audit_log` | 0 改动 |
| **F1.3 资产对账** | scanner 产出 `soc_scan_findings` → **扩展 F1.3 新增「发现维度」**遍历 findings 产 `TYPE_SHADOW`（**需改，非 0 改动**） |
| **F1.1 风险评分** | scanner 写 `soc_asset_ports` → `ports_score` 自动受益 | 0 改动 |
| **F4.2 推送场景 4** | 复用 `_find_new_shadows`（按 `TYPE_SHADOW + pending` 过滤）；需补 scanner 来源文案 | 小改文案 |

### 5.3 通信模型：以「拉（pull）」为主

**弃用「后端反向推送任务给扫描器」方案，采用拉模型**：

| 维度 | 推模型（否定） | 拉模型（选定 ✅） |
|---|---|---|
| NAT/防火墙穿透 | 后端需反向连扫描器，Kali 若 NAT 后必被挡 | 仅扫描器出向请求，天然穿透 |
| 扫描器离线处理 | 推送失败需重试/队列，复杂度高 | 任务留 `pending`，恢复自动认领，无丢失 |
| 与现有采集器一致 | 不一致（采集器都推，后端不连采集器） | 一致（采集器推、后端不连采集器） |
| 状态同步 | 双向长连，难维护 | 心跳单向 + 任务轮询，简单 |

> 拉模型下，后端**永远不需要知道扫描器的 IP 是否反向可达**——极大简化多机房/多子网部署。

### 5.4 三层在线检测信号

| 层 | 机制 | 实现 | 离线/异常判定 |
|---|---|---|---|
| **L1 存活（liveness）** | 扫描器主动心跳 | 每 30s `POST /api/v1/scan/agents/heartbeat` | 看门狗每 60s：`now - last_heartbeat > 90s` → `status='offline'` |
| **L2 数据通道（data-channel）** | 复用 `soc_source_health` | 每次推 discovery/port 写 `scanner:discovery`/`scanner:ports` 键 | `last_success_at` 超阈值 → 通道异常 |
| **L3 反向探活（可选）** | 后端 `GET scanner:9000/health` | 同 LAN 可达时作第二信号 | 不可达即告警（仅同 LAN 启用，NAT 留空） |

> **这正是 P4 缺口的解法**：192.168.0.2 凌晨中断无人知，根因是缺 L1/L2。扫描器上线即纳入 `soc_scanner_agents`，离线自动进通知 + 仪表板警告。
> L1 回答「进程还在吗」，L2 回答「还在正常产出数据吗」。两者独立——进程活着但 nmap 卡死（L1 正常、L2 停滞）也能被 L2 捕获。

### 5.5 新表清单

| 表名 | 用途 | 备注 |
|---|---|---|
| `soc_scanner_tasks` | 扫描任务记录（历史+可观测性） | **改名**（避开漏洞模块已占用的 `soc_scan_tasks`） |
| `soc_scan_targets` | 扫描目标清单（管理员配置） | 无冲突，保留原名 |
| `soc_scan_findings` | **新增**：扫描发现结果（与台账解耦） | 核心修复：scanner 不直接写 `soc_assets` |
| `soc_scanner_agents` | **新增**：扫描器注册/状态/心跳 | 无冲突（已 grep 确认） |

### 5.6 建表路径决策（硬伤 3 修复）

工程现状：`src/backend/alembic/versions/` 迁移图**碎片化**（多 head/多 root），**无仓库根 `alembic.ini`**，实际主要靠 `create_all` 建表。

**决策：双路径，路径 B 即时落地，路径 A 作为正式发布治理。**

- **路径 B（即时落地，推荐先走）**：在 SQLAlchemy models（`scan_models.py`）中定义模型，`Base.metadata.create_all` 在建表时自动建表（与当前工程实际一致，零迁移风险）。
- **路径 A（正式发布前治理）**：先把 alembic 合并为单一 head（`alembic merge`），再追加一份新迁移，并补仓库根 `alembic.ini`。此路径是 P4「Alembic 孤儿修订」治理的一部分，不阻塞本期功能。

> 文档内所有「新增表」描述均按路径 B 表述（models 定义），§13 注明路径 A 的收尾任务。

---

## 六、详细设计

### 6.1 采集器 `ScannerCollector`

#### 6.1.1 内部类结构

```python
# src/collectors/scanner/scanner_collector/collector.py

class ScannerCollector(BaseCollector):
    source_name = "scanner"
    supported_types = [DataType.DISCOVERY, DataType.PORT]  # 用 discovery 取代直接 asset

    async def collect(self, data_type: DataType) -> CollectResult:
        if data_type == DataType.DISCOVERY:
            return await self._collect_discovery()
        if data_type == DataType.PORT:
            return await self._collect_ports()
        raise NotImplementedError(f"不支持的 data_type: {data_type}")

    async def _collect_discovery(self) -> CollectResult:
        """
        内网资产发现模式（落 findings，不写台账）：
          1. 拉取所有 internal CIDR（scan_targets 配置 + soc_assets.network_segment 汇总）
          2. 每个 CIDR 跑 nmap -sn（ping scan）+ -O（OS 探测）
          3. 解析 XML，一律产出 discovery item
             - 已存在 IP：matched=true（F1.3 跳过）
             - 不存在 IP：matched=false（F1.3 产 shadow 来源）
          4. 返回 CollectResult(data_type=DISCOVERY, items=[...])
        """
        cidrs = self._resolve_target_cidrs()
        items: list[dict] = []
        for cidr in cidrs:
            xml = await self.nmap.run(["-sn", "-n", cidr])
            for host in parse_nmap_xml(xml).hosts:
                items.append(self._build_discovery_record(host, exposure="internal"))
        return CollectResult(source="scanner", data_type=DataType.DISCOVERY, items=items)

    async def _collect_ports(self) -> CollectResult:
        """
        公网暴露面扫描模式：
          1. 拉取所有 exposure_level='public' 的资产 IP
          2. 每个 IP 跑 nmap -sV -Pn --top-ports 1000
          3. 解析 XML，每个 open port 构造 PortRecord（asset_id 由后端反查）
        """
        targets = self._resolve_public_targets()
        items: list[dict] = []
        for target in targets:
            xml = await self.nmap.run([
                "-sV", "-Pn", "--top-ports", "1000",
                "--version-intensity", "5", target.ip,
            ])
            for host in parse_nmap_xml(xml).hosts:
                for port in host.ports:
                    items.append(self._build_port_record(target.asset_id, host, port))
        return CollectResult(source="scanner", data_type=DataType.PORT, items=items)

    async def test_connection(self) -> bool:
        return await self.nmap.is_available()
```

#### 6.1.2 端口子集策略（避免爆库）

公网扫描默认 `--top-ports 1000`，对一台公网资产平均产出 ~10 个 open port。按 73 台内网 + 20 台公网测算，全量公网一轮约 ~200 PortRecord，可接受。

> **生产安全门**：`mem_limit: 256m` + `pids_limit: 256` + 单 IP 扫描超时 300s。

#### 6.1.3 扫描目标解析

```python
def _resolve_target_cidrs(self) -> list[str]:
    """
    内网 CIDR 来源（按优先级）：
      1. scan_targets 表中 enabled=true 且 scope='internal' 的条目
      2. 从 soc_assets.network_segment 自动汇总（去重）
      3. config.yaml 中 defaults.internal_cidrs
    """

def _resolve_public_targets(self) -> list[ScanTarget]:
    """
    公网目标来源：
      1. scan_targets 表中 enabled=true 且 scope='public' 的条目
      2. soc_assets 中 exposure_level='public' 的所有资产 IP
    """
```

**设计要点**：CIDR **不全自动**。若仅从 `soc_assets` 派生，永远扫不到从未入库的影子资产——必须靠人工或路由器 ARP 表补充初始 CIDR。

### 6.2 后端同步 Handler（discovery + port 双管道）

#### 6.2.1 DiscoverySyncHandler（核心修复：只写 findings，永不写台账）

```python
# src/backend/app/services/sync_handlers/discovery_sync_handler.py

class DiscoverySyncHandler(BaseSyncHandler):
    data_type = "discovery"

    def _item_key(self, item: dict) -> str:
        return f"{item['scan_task_uuid']}:{item['asset_ip']}"

    def _handle_one(self, source: str, item: dict, db: Session) -> dict:
        existing = db.query(ScanFinding).filter(
            ScanFinding.scan_task_uuid == item["scan_task_uuid"],
            ScanFinding.asset_ip == item["asset_ip"],
        ).one_or_none()

        if existing:
            existing.last_seen = datetime.now(timezone.utc)
            existing.os_guess = item.get("os_guess") or existing.os_guess
            existing.mac_address = item.get("mac_address") or existing.mac_address
            existing.raw_data = item.get("raw_data", existing.raw_data)
            return {"updated": 1}

        # 反查是否已存在于台账（仅作提示，不写入台账）
        asset = db.query(Asset).filter(Asset.asset_ip == item["asset_ip"]).first()
        finding = ScanFinding(
            scan_task_uuid=item["scan_task_uuid"],
            asset_ip=item["asset_ip"],
            mac_address=item.get("mac_address"),
            os_guess=item.get("os_guess"),
            exposure=item.get("exposure", "internal"),
            discovery_source="scanner",
            matched_asset_id=asset.id if asset else None,  # 提示用，非空时 F1.3 跳过
            finding_status="new" if not asset else "known",
            first_seen=datetime.now(timezone.utc),
            last_seen=datetime.now(timezone.utc),
            raw_data=item.get("raw_data"),
        )
        db.add(finding)
        return {"created": 1}
```

> **为什么不直接写 `soc_assets`**：直接写台账会同时违背 ADR-2「只标记不自动纳管」并切断 F1.3 shadow 链路（F1.3 shadow 循环只遍历 Wazuh agents，已入库资产永不被判 shadow）。解耦后 `soc_scan_findings` 是「待确认清单」，台账写入仅在「一键纳管」时发生。

#### 6.2.2 PortSyncHandler（复用既有 AssetPort 模型）

```python
# src/backend/app/services/sync_handlers/port_sync_handler.py

class PortSyncHandler(BaseSyncHandler):
    data_type = "port"

    def _validate_one(self, item: dict) -> None:
        required = {"asset_ip", "port", "protocol"}
        missing = required - item.keys()
        if missing:
            raise ValueError(f"缺少字段: {missing}")
        if not (1 <= item["port"] <= 65535):
            raise ValueError(f"非法端口号: {item['port']}")

    def _item_key(self, item: dict) -> str:
        return f"{item['asset_ip']}:{item['port']}/{item['protocol']}"

    def _handle_one(self, source: str, item: dict, db: Session) -> dict:
        existing = db.query(AssetPort).filter(
            AssetPort.asset_ip == item["asset_ip"],
            AssetPort.port == item["port"],
            AssetPort.protocol == item["protocol"],
        ).one_or_none()

        if existing:
            existing.service = item.get("service") or existing.service
            existing.version = item.get("version") or existing.version
            existing.service_banner = item.get("service_banner") or existing.service_banner
            existing.last_seen = datetime.now(timezone.utc)
            existing.state = item.get("state", "open")
            # vulnerability 列：本期由 F-S2 留空，Phase 4（NSE）填充
            return {"updated": 1}
        else:
            asset = db.query(Asset).filter(Asset.asset_ip == item["asset_ip"]).first()
            port = AssetPort(
                asset_id=asset.id if asset else None,
                asset_ip=item["asset_ip"],
                port=item["port"],
                protocol=item["protocol"],
                state=item.get("state", "open"),
                service=item.get("service"),
                version=item.get("version"),
                service_banner=item.get("service_banner"),
            )
            db.add(port)
            return {"created": 1}
```

> `AssetPort` 模型与 `app/api/asset_ports.py`(CRUD) + `schemas/asset_port.py` 已存在，`PortSyncHandler` 仅补「采集→同步」管道，与既有人工 CRUD/查询**互补**，不重复定义模型。

#### 6.2.3 注册

```python
# src/backend/app/services/sync_handlers/__init__.py
SYNC_HANDLERS: dict[str, BaseSyncHandler] = {
    "asset": AssetSyncHandler(),
    "discovery": DiscoverySyncHandler(),   # ← 新增
    "port": PortSyncHandler(),             # ← 新增
}

# _SOURCE_HEALTH_KEYS 加入：
_SOURCE_HEALTH_KEYS = {
    "tplink": "tplink:collector",
    "wazuh": "wazuh:agents",
    "scanner": "scanner:discovery",       # ← 新增（发现通道）
    "scanner-port": "scanner:ports",      # ← 新增（端口通道）
}
```

#### 6.2.4 发现 → 台账的纳管流（替代 v1.0 直接写台账）

台账写入**仅**发生在用户确认时，由独立 API 完成：

```python
# src/backend/app/api/scan.py

@router.post("/findings/{finding_id}/adopt")
async def adopt_finding(
    finding_id: int,
    body: AdoptFindingRequest,           # { asset_name?, criticality?, owner?, business_unit? }
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "operator")),
):
    """
    一键纳管：把 soc_scan_findings 的一条发现转为 soc_assets 正式记录。
      - 新建 Asset(data_source="scanner", asset_status="active",
                   asset_ip=finding.asset_ip, mac_address=finding.mac_address,
                   os_name=finding.os_guess, ...)
      - criticality/owner/business_unit 由请求体补充（scanner 不自动覆盖，遵循 ADR-2）
      - finding.finding_status = "adopted"，finding.matched_asset_id = 新资产 id
      - 写审计日志（action="asset_adopt"）
    """
```

> 发现先落 `soc_scan_findings`，主资产列表默认不展示 `finding_status` 条目；「一键纳管」是显式、带权限、带审计的动作，杜绝 nmap -sn 瞬时/重复命中污染台账与风险评分。

### 6.3 数据模型

> 以下按路径 B（models 定义 → create_all）表述。涉及新列增量：v1.2 为 `soc_scanner_tasks` 加 6 列、`soc_scan_findings` 加 `scanner_id`、新增 `soc_scanner_agents`；v1.3 为 `soc_scanner_agents` 加 `created_by`、为 `soc_scanner_tasks` 加 `parent_task_id`。

```sql
-- soc_scanner_tasks：扫描任务记录（改名，避开漏洞模块 soc_scan_tasks）
CREATE TABLE soc_scanner_tasks (
    id              BIGSERIAL PRIMARY KEY,
    task_uuid       UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    mode            VARCHAR(20) NOT NULL,       -- 'internal' / 'public' / 'ports'
    scope           VARCHAR(20) NOT NULL,       -- 'manual' / 'scheduled' / 'auto'
    status          VARCHAR(20) NOT NULL DEFAULT 'pending',
                                                     -- 'pending'/'running'/'success'/'failed'/'cancelled'
    triggered_by    VARCHAR(50),
    target_summary  JSONB,
    parent_task_id  UUID,                        -- v1.3 F-3：重派溯源（克隆自哪条任务）
    target_scanner_id  VARCHAR(36),             -- 指定执行扫描器（pinned）
    scanner_id         VARCHAR(36),             -- 实际执行者（认领后回写）
    assign_mode        VARCHAR(12) NOT NULL DEFAULT 'auto',  -- 'auto'/'pinned'
    claimed_at         TIMESTAMPTZ,
    capabilities       JSONB,                   -- 任务所需能力快照，用于路由
    run_reason         VARCHAR(32) DEFAULT 'manual',  -- 'manual'/'scheduled'/'auto-shadow'
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at     TIMESTAMPTZ,
    duration_ms     INTEGER,
    items_scanned   INTEGER DEFAULT 0,
    items_created   INTEGER DEFAULT 0,
    items_updated   INTEGER DEFAULT 0,
    items_failed    INTEGER DEFAULT 0,
    error_message   TEXT,
    nmap_args       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_scanner_tasks_status ON soc_scanner_tasks(status);
CREATE INDEX idx_scanner_tasks_assign ON soc_scanner_tasks(assign_mode, status);
CREATE INDEX idx_scanner_tasks_started ON soc_scanner_tasks(started_at DESC);

-- soc_scan_targets：扫描目标清单（管理员配置，无冲突保留原名）
CREATE TABLE soc_scan_targets (
    id              BIGSERIAL PRIMARY KEY,
    target_uuid     UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    scope           VARCHAR(20) NOT NULL,        -- 'internal'（CIDR）/'public'（IP 或域名）
    value           VARCHAR(100) NOT NULL,
    description     VARCHAR(255),
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    exclude_ips     JSONB,
    added_by        VARCHAR(50),
    last_scan_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_scan_targets_enabled ON soc_scan_targets(enabled) WHERE enabled = TRUE;
CREATE UNIQUE INDEX uq_scan_targets_scope_value ON soc_scan_targets(scope, value);

-- soc_scan_findings：扫描发现结果（与台账解耦的核心）
CREATE TABLE soc_scan_findings (
    id                BIGSERIAL PRIMARY KEY,
    scan_task_uuid    UUID NOT NULL,             -- 关联 soc_scanner_tasks.task_uuid
    asset_ip          VARCHAR(64) NOT NULL,
    mac_address       VARCHAR(32),
    os_guess          VARCHAR(128),
    exposure          VARCHAR(16) NOT NULL DEFAULT 'internal',  -- 'internal'/'public'
    discovery_source  VARCHAR(32) NOT NULL DEFAULT 'scanner',
    scanner_id        VARCHAR(36),              -- v1.2：来源扫描器，便于溯源
    matched_asset_id  BIGINT,                    -- 反查 soc_assets.id（仅提示，非空时 F1.3 跳过）
    finding_status    VARCHAR(16) NOT NULL DEFAULT 'new',
                                                  -- 'new'/'known'/'adopted'/'ignored'
    first_seen        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen         TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_data          JSONB,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_scan_findings_ip ON soc_scan_findings(asset_ip);
CREATE INDEX idx_scan_findings_status ON soc_scan_findings(finding_status);
CREATE INDEX idx_scan_findings_task ON soc_scan_findings(scan_task_uuid);
CREATE INDEX idx_scan_findings_scanner ON soc_scan_findings(scanner_id);
CREATE UNIQUE INDEX uq_scan_findings_task_ip ON soc_scan_findings(scan_task_uuid, asset_ip);

-- soc_scanner_agents：扫描器注册/状态/心跳（v1.2 新增；v1.3 加 created_by）
CREATE TABLE soc_scanner_agents (
    id                  BIGSERIAL PRIMARY KEY,
    scanner_id         VARCHAR(36) NOT NULL UNIQUE,     -- UUID，注册时分配
    name               VARCHAR(100) NOT NULL,
    ip                 VARCHAR(64),
    capabilities       JSONB NOT NULL DEFAULT '[]'::jsonb,  -- ['internal','public','ports']
    reachable_subnets  JSONB NOT NULL DEFAULT '[]'::jsonb, -- ['192.168.0.0/24']
    status             VARCHAR(20) NOT NULL DEFAULT 'unknown',
                                                          -- 'online'/'offline'/'disabled'/'unknown'
    version            VARCHAR(32),
    running_tasks      INTEGER NOT NULL DEFAULT 0,
    last_heartbeat     TIMESTAMPTZ,
    api_key_hash       VARCHAR(255),                     -- API Key 哈希（不存明文）
    enabled            BOOLEAN NOT NULL DEFAULT TRUE,
    created_by         VARCHAR(50),                      -- v1.3 M-3：注册操作人，审计溯源
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_scanner_agents_status ON soc_scanner_agents(status);
CREATE INDEX idx_scanner_agents_enabled ON soc_scanner_agents(enabled) WHERE enabled = TRUE;
```

**关于 `soc_assets.asset_status` 枚举（v1.1 决定不修改）**：发现已解耦到 `soc_scan_findings`，台账侧无须表示「待纳管」状态——纳管后资产直接用既有 `active`/`online`。发现态由 `soc_scan_findings.finding_status`（`new`/`known`/`adopted`/`ignored`）表达，前端字典表为该枚举补中文标签即可。

### 6.4 API 端点

#### 6.4.1 人类用户端点

| 端点 | 方法 | 权限 | 说明 |
|---|---|---|---|
| `/api/v1/scan/run` | POST | operator / admin | 在控制面建任务（body 含 `mode`/`targets`/`assign_mode`/`target_scanner_id`/`schedule`/`nmap_args`/`notify`）；不再直接调扫描器，任务经 `pending` 由扫描器拉取 |
| `/api/v1/scan/tasks` | GET | viewer+ | 任务历史（分页 + status 过滤；含 `scanner_id`/`target_scanner_id`/`assign_mode`） |
| `/api/v1/scan/tasks/{uuid}` | GET | viewer+ | 单任务详情 |
| `/api/v1/scan/tasks/{uuid}/cancel` | POST | operator / admin | 置 `cancelled` 状态位，扫描器下次轮询读到中止（拉模型下改为状态信号） |
| `/api/v1/scan/targets` | GET/POST | viewer+ / operator+admin | 目标清单 / 新增 |
| `/api/v1/scan/targets/{id}` | PATCH/DELETE | operator+admin / admin | 修改 / 删除 |
| `/api/v1/scan/findings` | GET | viewer+ | 发现清单（status/ip/exposure 过滤） |
| `/api/v1/scan/findings/{id}/adopt` | POST | operator / admin | 一键纳管（写 `soc_assets`） |
| `/api/v1/scan/findings/{id}/ignore` | POST | operator / admin | 忽略（标记 `ignored`） |
| `/api/v1/scan/agents` | GET/POST | viewer+ / admin | 扫描器列表 / 注册（生成 scanner_id + API Key，填能力/子网） |
| `/api/v1/scan/agents/{id}` | PATCH/DELETE | admin | 启用/禁用/编辑 / 注销（软删） |

**权限矩阵（X1 扩展）**：菜单 `/assets/scan`（顶级），按钮权限：

```python
# soc_menus.permissions JSONB
[
    {"title": "触发扫描", "authMark": "scan_run"},
    {"title": "管理目标", "authMark": "scan_target_manage"},
    {"title": "查看历史/发现", "authMark": "scan_view"},
    {"title": "纳管/忽略发现", "authMark": "scan_finding_manage"},
]
```

| 角色 | scan_view | scan_run | scan_target_manage | scan_finding_manage |
|---|---|---|---|---|
| admin | ✓ | ✓ | ✓ | ✓ |
| operator | ✓ | ✓ | ✓ | ✓ |
| viewer | ✓ | ✗ | ✗ | ✗ |
| auditor | ✓ | ✗ | ✗ | ✗ |

> 后端依赖（**待核实**：`require_role` 真实签名需对照本项目 X1 权限模型确认，落库前必须核对是否存在 `require_admin` 可复用）。

#### 6.4.2 扫描器端点（X-API-Key 鉴权）

| 端点 | 方法 | 权限 | 说明 |
|---|---|---|---|
| `/api/v1/scan/agents/heartbeat` | POST | scanner（API Key） | 扫描器心跳 upsert 状态 |
| `/api/v1/scan/tasks/pending` | GET | scanner（API Key） | 拉取可认领任务（`?scanner_id=&caps=`） |
| `/api/v1/scan/tasks/{uuid}/claim` | PATCH | scanner（API Key） | 原子认领（pending→running） |
| `/api/v1/scan/tasks/{uuid}/report` | PATCH | scanner（API Key） | 回写结果（success/failed + counts） |

> **认证分层**：人类端点用现有 `require_role`（X1 权限矩阵）；扫描器端点用 `X-API-Key`（与 `MiniSOCClient` 现有机制一致），后端按 `api_key_hash` 反查 `scanner_id`。扫描器**无权**调用人类端点，只能心跳/拉任务/认领/回写——权限边界清晰。

#### 6.4.3 扫描器鉴权依赖（v1.3 O-1 补全）

```python
# src/backend/app/api/deps.py（新增，镜像既有 require_api_key @ :59）
async def require_scanner_api_key(
    request: Request,
    db: Session = Depends(get_db),
) -> ScannerAgent:
    """Scraper 端点鉴权：从 X-API-Key 反查 scanner_id，注入 request.state。

    与 require_api_key（普通采集器）的区别：scanner key 同时携带 scanner_id，
    用于心跳/拉任务/认领时回写 scanner_id 字段。
    """
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        raise HTTPException(status_code=401, detail="missing X-API-Key")
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    scanner = db.query(ScannerAgent).filter(
        ScannerAgent.api_key_hash == key_hash,
        ScannerAgent.enabled == True,
    ).first()
    if not scanner:
        raise HTTPException(status_code=403, detail="invalid or disabled scanner")
    request.state.scanner_id = scanner.scanner_id
    return scanner
```

```python
# src/backend/app/api/scan_agents.py
@router.post("/agents/heartbeat")
async def heartbeat(
    body: HeartbeatRequest,
    scanner: ScannerAgent = Depends(require_scanner_api_key),
    db: Session = Depends(get_db),
):
    scanner.last_heartbeat = datetime.now(timezone.utc)
    scanner.ip = body.ip or scanner.ip
    scanner.version = body.version or scanner.version
    scanner.capabilities = body.capabilities
    scanner.reachable_subnets = body.reachable_subnets
    scanner.running_tasks = body.running_tasks
    scanner.status = "online"
    db.commit()
    return {"status": "online", "last_heartbeat": scanner.last_heartbeat}
```

### 6.5 审计 + 合规

每次扫描写 `soc_audit_logs`（与 CLAUDE.md「对账/EOL 落审计」一致）；「一键纳管」「忽略发现」同样落审计（`action="asset_adopt"` / `"finding_ignore"`）。scanner-collector 启动/结束也写一次，便于追溯自动扫描来源。

---

## 七、多扫描器编排

### 7.1 能力声明与注册

扫描器首次上线，运维在控制面「注册」生成记录，下发 `scanner_id`（UUID）+ `API Key`；扫描器心跳时持续上报实时能力：

```json
// POST /api/v1/scan/agents/heartbeat  body
{
  "scanner_id": "a1b2c3d4-...",
  "ip": "192.168.0.45",
  "version": "1.2.0",
  "capabilities": ["internal", "public", "ports"],
  "reachable_subnets": ["192.168.0.0/24", "10.0.0.0/24"],
  "running_tasks": 0
}
```

`soc_scanner_agents` 据此 upsert：`status`、`last_heartbeat`、`version`、`capabilities`、`reachable_subnets`、`running_tasks`、`created_by`（注册时记录）。

### 7.2 任务派发路由算法

`central_scan_scheduler` 或手动 `POST /scan/run` 建任务时，确定执行扫描器：

| 场景 | `assign_mode` | 目标扫描器确定方式 |
|---|---|---|
| 手动指定 | `pinned` | `target_scanner_id` 显式给定（UI 下拉选 192.168.0.45） |
| 自动路由（internal） | `auto` | 按任务 CIDR 匹配各扫描器 `reachable_subnets`，派给可达者；多个可达取 `running_tasks` 最小者（负载均衡） |
| 自动路由（public） | `auto` | 派给声明 `public` 能力且 `status=online` 者（取 `running_tasks` 最小） |
| 自动路由（无匹配） | `auto` | 无可达扫描器 → 任务保持 `pending` + 告警「无可用扫描器」 |

> **192.168.0.45 自然归属**：`internal` 任务 CIDR `192.168.0.0/24` 匹配其 `reachable_subnets`，自动派给它。

### 7.3 认领竞态（避免多扫描器抢同一任务）

扫描器 `GET /scan/tasks/pending` 拿到候选后，用**原子事务**认领：

```python
# PATCH /api/v1/scan/tasks/{uuid}/claim
task = db.query(ScannerTask).filter(
    ScannerTask.task_uuid == uuid,
    ScannerTask.status == "pending",
    ScannerTask.target_scanner_id.in_([scanner_id, None]),  # 指定我或广播
).with_for_update().first()
if not task:
    return {"claimed": False}  # 已被别人认领，跳过
task.status = "running"
task.scanner_id = scanner_id        # 回写实际执行者
task.claimed_at = now()
db.commit()
return {"claimed": True, "nmap_args": task.nmap_args, "targets": task.target_summary}
```

- `with_for_update()` 行锁保证并发下只有一个扫描器能把 `pending` 翻成 `running`。
- `target_scanner_id=None` 的任务对所有扫描器可见（广播），认领后即绑定执行者。
- 扫描器认领后若崩溃，看门狗检测 `running` 超时（> 6h 或 > 预期 3x）标 `failed` + 自动重派（见 §8.1）。

### 7.4 心跳/轮询循环（扫描器侧，取代内嵌 cron）

```python
# collectors/scanner/run_scanner.py（心跳+拉任务循环，不再内嵌 cron）
async def loop(scanner_id, client):
    while True:
        await client.heartbeat(scanner_id, caps, running=current_running)  # 1. 心跳（每 30s）
        task = await client.fetch_pending(scanner_id, caps)                 # 2. 拉取可认领任务
        if task:
            claimed = await client.claim(task["uuid"], scanner_id)          # 3. 原子认领
            if claimed:
                result = await run_nmap(task["nmap_args"], task["targets"]) # 4. 执行 nmap
                await client.sync("scanner", task["data_type"], result.items)  # 5. 推数据
                await client.report_status(task["uuid"], "success", counts=...)  # 6. 回写状态
        await asyncio.sleep(10)  # 轮询间隔
```

> **调度在哪？** 不再有扫描器侧 cron。internal/public 的「每天 03:00/04:00」由**控制面 `central_scan_scheduler` 按固定间隔建任务**（§8.2）；扫描器只负责认领执行。临时任务（US-2）由用户在 UI 建。

---

## 八、后端调度器（lifespan 注册，复用现有范式）

复用 main.py 已成熟的 **lifespan + scheduler 范式**（`start_alert_digest_scheduler` / `start_cisa_kev_scheduler` / `start_push_scheduler` 均为 `lifespan` 内启动的 asyncio 任务）。本方案新增两个调度，零新基础设施。

```python
# main.py lifespan 内新增（沿用现有范式）
from app.services.scanner_watchdog_scheduler import start_scanner_watchdog, stop_scanner_watchdog
from app.services.central_scan_scheduler import start_central_scan_scheduler, stop_central_scan_scheduler

start_scanner_watchdog()        # 每 60s 检测离线 + 超时任务重派
start_central_scan_scheduler()  # 固定间隔对齐 03:00/04:00 建 internal/public 任务
# finally 段对应 stop_*
```

> **范式依据（已代码级核实）**：现有 scheduler 均为固定秒数间隔——`cisa_kev_service.py:223` `expected_interval_s=86400` + `:252` `asyncio.sleep(timedelta(hours=24))`；`alert_group_snapshot_scheduler.py:23` `INTERVAL_SECONDS = 6 * 3600` + `:73` sleep 该值。全仓无 cron 解析依赖。故本方案**不引入 cron 字符串**，与现有范式保持一致（v1.3 F-1）。

### 8.1 `scanner_watchdog_scheduler`（含 v1.3 F-2 独立 session + F-3 超时重派）

```python
async def _watchdog_tick():
    """每 60s 跑一次：检测离线 + 检测超时 running 任务。
    遵循 CLAUDE.md 教训（:1159 独立 session 防 rollback 互杀；:1189 record_failure 写不进去需独立 session）。
    """
    with SessionLocal() as session:   # 关键1：每个 tick 开新 session
        try:
            # ----- L1 检测：离线扫描器 -----
            cutoff = datetime.now(timezone.utc) - timedelta(seconds=90)
            offline = session.query(ScannerAgent).filter(
                ScannerAgent.enabled == True,
                ScannerAgent.status != "offline",
                ScannerAgent.last_heartbeat < cutoff,
            ).all()

            for a in offline:
                # 关键2：dedup——避免同台 scanner 在最近 N 分钟内被重复通知
                if _already_notified_recently(session, a.scanner_id, "scanner_offline", lookback_minutes=10):
                    continue
                try:
                    a.status = "offline"
                    notify_scanner_offline(a)   # 关键3：notify 用独立 session 不污染本 tick
                    _record_notification_sent(session, a.scanner_id, "scanner_offline")
                except Exception:
                    # 关键4：单条失败不影响其他扫描器
                    logger.exception("watchdog: 处理 scanner %s 失败", a.scanner_id)
                    session.rollback()
                    continue

            # ----- F-3 检测：超时 running 任务 → 标 failed + 自动重派 -----
            stuck_cutoff = datetime.now(timezone.utc) - timedelta(hours=6)
            stuck = session.query(ScannerTask).filter(
                ScannerTask.status == "running",
                ScannerTask.started_at < stuck_cutoff,
            ).all()
            for t in stuck:
                try:
                    t.status = "failed"
                    t.error_message = "watchdog: running 超时（>6h）"
                    # 自动 clone 一条新 pending 让路由重新选（不强制原 scanner）
                    new_task = ScannerTask(
                        mode=t.mode, scope=t.scope, target_summary=t.target_summary,
                        target_scanner_id=None, scanner_id=None, status="pending",
                        run_reason=t.run_reason, parent_task_id=t.task_uuid,
                        capabilities=t.capabilities, nmap_args=t.nmap_args,
                    )
                    session.add(new_task)
                except Exception:
                    logger.exception("watchdog: 重派 task %s 失败", t.task_uuid)
                    session.rollback()
                    continue

            session.commit()
        except Exception:
            # 关键5：整 tick 失败时整体 rollback + 退避 60s
            session.rollback()
            logger.exception("watchdog tick failed, will retry in 60s")
            await asyncio.sleep(60)
```

**重派语义（v1.3 F-3 约定）**：
1. 原 `running` 任务 → `failed`，`error_message = "watchdog: running 超时（>6h）"`
2. 自动 clone 新任务：`target_scanner_id=None`（让 auto 路由重选）、`run_reason` 保留原始值、`parent_task_id=原 task_uuid`
3. 不强制重派到原 scanner——若原 scanner 已 offline，让 auto 路由选其他可达 scanner
4. **重派次数上限：单任务链最多 3 次**（避免「扫描器永久卡死 → 任务无限重派」耗资源）；超限后停止重派 + admin 通知

> dedup 复用 `soc_notifications` 已发字段（`_already_notified_recently` + `_record_notification_sent` 落在 `notification_dedup.py`，与现有 push_notification_service 复用一套）。

### 8.2 `central_scan_scheduler`（v1.3 F-1：固定秒数间隔，非 cron）

```python
# v1.2 设计意图：internal 03:00 / public 04:00；落地为每 24h、启动后先 sleep 到下个目标时刻
INTERVAL_SECONDS = 24 * 3600  # 每天一次

# 期望首次执行时刻（24h 制）。每天 03:00 / 04:00 与固定 24h 间隔等价。
EXEC_HOURS = {
    "internal": 3,
    "public":   4,
}

async def _seconds_until_next_exec(hour_24: int) -> int:
    """到下个 hour_24 点的秒数（≥60s，避免启动后立即触发）。"""
    now = datetime.now(timezone.utc)
    target = now.replace(hour=hour_24, minute=0, second=0, microsecond=0)
    if target <= now or (target - now).total_seconds() < 60:
        target += timedelta(days=1)
    return int((target - now).total_seconds())

async def _central_scan_loop():
    """与现有 alert_digest_scheduler 等保持完全相同的范式。"""
    for mode, hour in EXEC_HOURS.items():
        asyncio.create_task(_mode_loop(mode, hour))
    while True:
        await asyncio.sleep(3600)

async def _mode_loop(mode: str, hour_24: int):
    delay = await _seconds_until_next_exec(hour_24)
    logger.info("central_scan[%s] first run in %ds (at %02d:00 UTC)", mode, delay, hour_24)
    await asyncio.sleep(delay)
    while True:
        try:
            create_scan_task(mode=mode, scope="scheduled", assign_mode="auto",
                             run_reason="scheduled",
                             target_summary=_resolve_targets(mode))
        except Exception:
            logger.exception("central_scan[%s] tick failed", mode)
            await asyncio.sleep(3600)  # 出错后 1h 再试（与 alert_digest_scheduler.py:87 同款）
            continue
        await asyncio.sleep(INTERVAL_SECONDS)
```

**消除项**：`_should_fire(spec, now)` 函数、`croniter`/`cron_descriptor` 依赖、CRON 字典字符串值。

---

## 九、与现有功能的联动

### 9.1 F1.3 资产对账（**需扩展「发现维度」，非 0 改动**）

v1.0 假设 scanner 直接写 `soc_assets` 后 F1.3「自动判定 shadow」——实测不成立（F1.3 shadow 循环只遍历 Wazuh agents，`asset_reconciliation.py:247-315`）。**改为扩展 F1.3**：在现有「遍历 Wazuh agents」与「遍历台账侧」两个分支之外，**新增第三分支「遍历 `soc_scan_findings`」**：

```python
# src/backend/app/services/asset_reconciliation.py（扩展，伪码）
# ---- 遍历 scanner 发现：找台账缺失的影子资产
for f in findings:
    if f.finding_status in ("adopted", "ignored"):
        continue  # 已处置，不再产 shadow
    if f.matched_asset_id:
        continue  # 已在台账，跳过
    # 去重：按 asset_ip 避免每轮重复产 shadow（R7 修正）
    if _shadow_exists_for_ip(f.asset_ip, since_window):
        continue
    rows.append(AssetReconciliation(
        run_id=run_id, task_id=task_id,
        asset_id=None,                         # 资产不在台账
        reconciliation_type=TYPE_SHADOW,
        details={
            "source": "scanner",               # 标注来源
            "asset_ip": f.asset_ip,
            "mac_address": f.mac_address,
            "os_guess": f.os_guess,
            "suggestion": "内网扫描发现但未纳管，建议确认后补录或一键纳管",
        },
        status=STATUS_PENDING, created_at=now,
    ))
```

**重点**：scanner 是**新增 shadow 路径之一**（与 Wazuh 并列），而非「零改动白嫖」。F1.3 扩展后方可闭环。

### 9.2 F4.2 推送场景 4「影子资产」（**复用过滤 + 小改文案**）

F4.2 `_find_new_shadows`（`push_notification_service.py:322-351`）实际按 `TYPE_SHADOW + status='pending' + created_at>=since` 过滤（**不要求 `asset_id=None`**）。scanner 源 shadow 行**会被自动消费**，无需改过滤逻辑。

**需小改之处**：当前通知文案写死 Wazuh 语境。scanner 源 shadow 的 `details` 含 `source:"scanner"` 与 `asset_ip`，应据此**分支文案**：

```python
# push_notification_service.py check_shadow_assets（补充 scanner 来源）
d = r.details or {}
if d.get("source") == "scanner":
    ip = d.get("asset_ip", "")
    os_part = d.get("os_guess") or "系统未知"
    content = (f"内网扫描发现资产（IP {ip}，系统 {os_part}），"
               f"但台账中无对应记录。建议确认是否需补录入台账，"
               f"或通过「一键纳管」处理。")
    link_path = "/assets/scan/findings"
else:
    # 维持原 Wazuh 文案
    ...
```

### 9.3 F1.1 风险评分（0 改动，成立）

scanner 写入 `soc_asset_ports` 后，`POST /api/v1/assets/risk/batch-score` 重算：`ports_score` 维度直接从 `soc_asset_ports` 取数，公网资产端口从 0 → 5+，`data_classification` 配合 `exposure_level="public"` 触发高分。

### 9.4 `/data/health` 三层聚合（1 行改动）

`_source_status()` 自动遍历 `soc_source_health.source_key`，注册 `scanner:discovery` / `scanner:ports` 后自动出现；新增 `soc_scanner_agents.status` 在仪表板合并展示（`scanner:*` 通道 + 扫描器在线状态双信号）。

### 9.5 增量重扫（F1.3 shadow → 单 IP 重扫）

v1.2 改为**控制面建 `run_reason='auto-shadow'` 任务 → 路由给该 IP 子网扫描器**，无需扫描器暴露 HTTP（更符合拉模型）。

---

## 十、安全与可靠性

### 10.1 容器安全（拆分内网/公网网络模式）

```yaml
# docker-compose.yaml 新增 service
# 内网发现：必须 host 网络才能发 ARP（nmap -sn）
scanner-collector-internal:
  build: ./scanner
  container_name: minisoc-scanner-internal
  restart: unless-stopped
  init: true
  cap_add: [NET_RAW, NET_ADMIN]
  network_mode: host                     # ARP 需要 L2 可见
  environment:
    # host 网络下无 docker 桥，MINISOC_URL 指向宿主机 LAN IP
    - MINISOC_URL=${MINISOC_URL:-http://192.168.0.102:8000}
    - MINISOC_API_KEY=${MINISOC_API_KEY}
    - SCAN_MODE=internal
    - SCAN_INTERNAL_CIDRS=192.168.0.0/24
    - SCAN_INTERVAL_INTERNAL=86400
    - SCAN_MAX_RATE=100
  mem_limit: 256m
  cpus: 1.0
  pids_limit: 256

# 公网扫描：走默认 bridge + NAT 出网
scanner-collector-public:
  build: ./scanner
  container_name: minisoc-scanner-public
  restart: unless-stopped
  init: true
  cap_add: [NET_RAW, NET_ADMIN]
  extra_hosts: ["host.docker.internal:host-gateway"]
  environment:
    - MINISOC_URL=${MINISOC_URL:-http://host.docker.internal:8000}
    - MINISOC_API_KEY=${MINISOC_API_KEY}
    - SCAN_MODE=public
    - SCAN_INTERVAL_PUBLIC=86400
    - SCAN_MAX_RATE=100
    - SCAN_USER_AGENT=AI-miniSOC-Scanner/1.3 (+admin: xiejava@xiejava.dpdns.org)
  mem_limit: 256m
  cpus: 1.0
  pids_limit: 256
```

> **M5 修正**：v1.0 同 service 内同时写 `network_mode: host` 与 `MINISOC_URL=host.docker.internal`（矛盾：host 网络无 docker 桥）。拆分为两个 service profile——内网用 host（ARP 需要，回连用宿主机 LAN IP），公网用 bridge（NAT 出网 + `host.docker.internal`）。

### 10.2 资源限制

| 维度 | 限制 | 触底动作 |
|---|---|---|
| 单 IP 扫描超时 | 300s | subprocess.kill() + 记 source_health.failure |
| 全网扫描时长 | 6h（防夜间跨日） | 强制 break |
| nmap rate | `--max-rate 100` | 防止生产网拥塞 |
| 数据库事务 | `BaseSyncHandler` 已实现批 100 条 commit | 防止长事务 |
| Docker 内存 | 256Mi | OOM kill → 自动重启 + 审计 |
| Docker PID | 256 | fork bomb 防护 |

### 10.3 扫描合法性

- **仅扫自有资产**：公网扫描目标必须先在 `soc_scan_targets` 注册或 `exposure_level="public"`，无授权不入库
- **身份暴露**：`User-Agent: AI-miniSOC-Scanner/1.3 (+admin: xiejava@xiejava.dpdns.org)`，便于白帽审计 / 误伤溯源
- **审计全留痕**：每次扫描写 `soc_audit_logs`（含 nmap_args、target 列表、耗时）；纳管/忽略发现亦留痕
- **执行权限分层（X1）**：仅 admin/operator 可触发与纳管，viewer 只读
- **离线扫描模式**：`dry_run=true` 时不写库，仅打印预期变更（生产上线前强制验证步骤）

### 10.4 死信 + 重试

复用 `BaseSyncHandler` 机制：单条失败 → `soc_sync_dead_letter`；采集器侧 `MiniSOCClient` 已实现 3 次重试 + 指数退避；`/data/health` 自动显示 `scanner:discovery` / `scanner:ports` 健康度。

---

## 十一、指标体系（可观测性）

> 遵循 P4「后台任务执行可观测性」精神，扫描器与控制面指标集中暴露。

| 指标 | 定义 | 目标/告警阈值 |
|---|---|---|
| **扫描器在线率** | `online / 总 enabled` | < 100% → 告警（单台离线即告警） |
| **任务派发成功率** | `success+running / 建任务总数` | < 95% 持续 24h → 排查 |
| **平均认领时延** | `claimed_at - created_at` 均值 | > 60s → 扫描器轮询过慢或过载 |
| **离线告警数** | 看门狗触发的 offline 通知数 | 趋势上升 → 网络/主机稳定性问题 |
| **L2 数据停滞** | `now - last_success_at(scanner:*)` | > 25h（约一个扫描周期+余量）→ 通道异常 |
| **任务失败率** | `failed / 总` | > 5% → 扫描器 nmap 异常 |

指标落点：`soc_scanner_agents.status`（L1）+ `soc_source_health` 键（L2）+ `soc_scanner_tasks` 统计（派发/认领/失败）。仪表板「采集器健康」页合并三类信号。

#### L3 不可用场景的回退指标（v1.3 O-2，NAT 后/异地/严格防火墙）

| 场景 | 判定 |
|---|---|
| L1 正常 + L2 正常 | **在线**（与原 6 指标定义一致） |
| L1 正常 + L2 停滞 > 25h | **数据流异常但进程存活**（可能 nmap 卡死，需查 nmap 进程） |
| L1 离线 + L2 正常 | **数据流正常但心跳丢失**（可能网络抖动；不立即告警，30min 后 L2 也停滞则升级为离线） |
| L1 离线 + L2 停滞 | **离线**（与原 6 指标定义一致） |
| L3 不可用（NAT 后） | **不参与判定**——L1 + L2 双信号合并决策 |

> L3 仅同 LAN 场景启用；NAT/异地扫描器留空不判定。

---

## 十二、部署形态（192.168.0.45 Kali）

### 12.1 容器 vs 裸机

| 方式 | 优劣 | 推荐 |
|---|---|---|
| **容器（推荐）** | `cap_add: [NET_RAW, NET_ADMIN]`，镜像自带 nmap；运维标准化、易升级、易扩多扫描器 | ✅ 首选 |
| 裸机（Kali 自带 nmap） | 省去容器，但进程管理/自愈/升级靠 systemd 手写，多扫描器不一致 | 仅当容器被禁时使用 |

### 12.2 网络模式（拆分内网/公网）

- **内网发现（ARP）**：`network_mode: host`，回连后端用宿主机 LAN IP `http://192.168.0.102:8000`（host 网络无 docker 桥）
- **公网扫描**：`bridge` + `extra_hosts: host.docker.internal:host-gateway`，`MINISOC_URL=http://host.docker.internal:8000`

> 192.168.0.45 与后端 192.168.0.102 同 LAN，L3 反向探活可启用；异地/NAT 后关闭 L3。

### 12.3 API Key 下发

- 控制面 `POST /scan/agents` 注册时生成 `scanner_id` + `API Key`（明文仅返回一次），哈希存 `soc_scanner_agents.api_key_hash`
- 部署 192.168.0.45 时通过环境变量注入：`MINISOC_API_KEY=<key>`、`SCANNER_ID=<uuid>`、`MINISOC_URL=http://192.168.0.102:8000`
- 密钥轮换：`PATCH /scan/agents/{id}` 重新生成 Key，旧 Key 失效

```bash
# /etc/environment 或 systemd unit（推荐用 systemd EnvironmentFile=）
SCANNER_ID=<由控制面 POST /scan/agents 返回的 UUID>
SCANNER_API_KEY=<由控制面 POST /scan/agents 返回的明文 Key，仅显示一次>
MINISOC_URL=http://192.168.0.102:8000

# 可选
HEARTBEAT_INTERVAL=30
POLL_INTERVAL=10
SCAN_USER_AGENT="AI-miniSOC-Scanner/1.3 (+admin: xiejava@xiejava.dpdns.org)"

# 注：MINISOC_API_KEY 是普通采集器（tplink/wazuh）的 Key，
# SCANNER_API_KEY 是 scanner 专用——两类身份独立。
```

### 12.4 多扫描器标识

每台扫描器独立 `scanner_id` + `API Key`，心跳上报独立 `ip`/`capabilities`/`reachable_subnets`。控制面据此做 §7.2 路由。

### 12.5 docker-compose 部署示例片段（v1.3 O-3）

```yaml
# src/collectors/docker-compose.yaml 增量片段
scanner-collector:
  build:
    context: .
    dockerfile: scanner/Dockerfile
  container_name: minisoc-scanner-collector
  restart: unless-stopped
  init: true   # 同 CLAUDE.md 已知：tini 收尸避免僵尸进程

  # 网络模式：内网扫描必须 host 才能发 ARP/ICMP 探测；公网扫描走默认 bridge + host.docker.internal
  network_mode: host

  environment:
    - SCANNER_ID=${SCANNER_ID}
    - MINISOC_API_KEY=${SCANNER_API_KEY}
    - MINISOC_URL=http://192.168.0.102:8000       # host 网络下 docker bridge 不可用，直接用宿主机 LAN IP
    - HEARTBEAT_INTERVAL=30
    - POLL_INTERVAL=10
    - NMAP_BINARY=/usr/bin/nmap
    - SCAN_USER_AGENT=AI-miniSOC-Scanner/1.3 (+admin: xiejava@xiejava.dpdns.org)

  mem_limit: 256m
  cpus: 1.0
  pids_limit: 256
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"
```

> **运维常见疑问**：「为什么不用 host.docker.internal？」——host 网络模式下容器直接共享宿主机网络栈，docker bridge 不存在，故解析失败。直接用宿主机 LAN IP 即可。

---

## 十三、实施步骤

> v1.1 的 Phase 1~4 与 v1.2 的 S1~S12 正交，合并为统一实施计划。

### Phase 1：MVP — 公网扫描 + 端口落库（约 1.5 周）

| # | 任务 | 文件 | 工时 |
|---|---|---|---|
| 1.1 | 新增 `PortSyncHandler`（复用 `AssetPort`） | `services/sync_handlers/port_sync_handler.py` | 0.5d |
| 1.2 | 注册 2 个 handler + 健康键 | `services/sync_handlers/__init__.py` | 0.1d |
| 1.3 | 编写 `ScannerCollector` skeleton + nmap_runner | `collectors/scanner/scanner_collector/` | 1d |
| 1.4 | 公网扫描 `_collect_ports()` + XML 解析 | 同上 | 1d |
| 1.5 | 写 `run_scanner.py` + Dockerfile（拆分 internal/public） | `collectors/scanner/` | 0.5d |
| 1.6 | 接入 docker-compose（双 service profile）+ deploy_collectors.sh | `collectors/docker-compose.yaml` | 0.5d |
| 1.7 | 端到端：mock XML → POST /data/sync → 验证 DB + source_health | `tests/integration/test_scanner_e2e.py` | 1d |
| 1.8 | 生产部署 + dry_run 验证 1 天 | ops | 1d |

**验收**：生产一台公网资产扫描后，`soc_asset_ports` 新增记录，`/data-health` 出现 `scanner:ports=healthy`。

### Phase 2：内网发现 + 解耦 + F1.3 扩展 + 控制面（约 3.5 周）

| # | 任务 | 文件 | 工时 | 依赖 |
|---|---|---|---|---|
| 2.1 | 新增 `ScannerAgent` 模型 + 建表（路径 B，含 created_by / parent_task_id） | `api/scan_models.py` | 0.5d | §5.6 |
| 2.2 | `soc_scanner_tasks` 增量列迁移 + `ScanFinding.scanner_id` | `api/scan_models.py` | 0.3d | v1.1 表 |
| 2.3 | 新增 `DiscoverySyncHandler`（落 `soc_scan_findings`） | `services/sync_handlers/discovery_sync_handler.py` | 0.5d | 2.1 |
| 2.4 | `_collect_discovery()` 实现 + CIDR 解析（落 findings，不写台账） | `collectors/scanner/scanner_collector/collector.py` | 1d | 2.3 |
| 2.5 | **扩展 F1.3「发现维度」**：遍历 `soc_scan_findings` 产 scanner 源 shadow（按 IP 去重） | `services/asset_reconciliation.py` | 1d | — |
| 2.6 | **F4.2 文案分支**：scanner 源 shadow 用独立通知文案 | `services/push_notification_service.py` | 0.5d | 2.5 |
| 2.7 | 扫描器端点：heartbeat / pending / claim / report（含 `require_scanner_api_key`） | `api/scan_agents.py`, `api/scan_tasks.py` | 1.5d | 2.1 |
| 2.8 | 人类端点：agents CRUD + `/scan/run` 改派发 + 路由算法 | `api/scan.py` | 1.5d | 2.1,2.2 |
| 2.9 | `scanner_watchdog_scheduler`（独立 session + dedup + 超时重派） | `services/scanner_watchdog_scheduler.py` + `notification_dedup.py` | 0.5d | 2.7 |
| 2.10 | `central_scan_scheduler`（固定秒数间隔对齐 + auto 路由） | `services/central_scan_scheduler.py` | 0.5d | 2.8 |
| 2.11 | 扫描器 `run_scanner.py` 改写：内嵌 cron → 心跳+拉任务循环 | `collectors/scanner/run_scanner.py` | 1d | 2.7 |
| 2.12 | `MiniSOCClient` 增 `heartbeat/fetch_pending/claim/report` | `collectors/.../sync_client.py` | 0.5d | 2.7 |
| 2.13 | F4.2 增「扫描器离线」通知类型 | `services/push_notification_service.py` | 0.5d | 2.9 |
| 2.14 | API `/findings` + 纳管/忽略 | `api/scan.py`, `schemas/scan.py` | 1.5d | 2.8 |
| 2.15 | 前端控制面：扫描器管理 + 任务下发/编排 + 健康看板（见控制面原型） | `frontend/src/views/asset/scan/*` | 2d | 2.8,2.9 |
| 2.16 | 部署 192.168.0.45：compose + Key 下发 + dry_run 验证 | ops | 1d | 2.11,2.12 |

**验收**：
1. 192.168.0.45 注册上线 → 仪表板显示 online + 最后心跳刷新
2. UI 建一次 internal 任务（指定 192.168.0.45）→ 扫描器 10s 内认领 → 推 discovery → findings 入
3. 手动停掉 192.168.0.45 进程 → 看门狗 90s 后标 offline + 通知
4. 多扫描器：两台 reachable_subnets 不同 → internal 任务按 CIDR 各派各的
5. 生产跑一次内网扫描 → `soc_scan_findings` 入 N 条 `new` → F1.3 扩展产出 scanner 源 shadow → F4.2 推站内通知（scanner 文案）→ 前端「一键纳管」写 `soc_assets`

### Phase 3：体验增强（约 1 周）

| # | 任务 | 文件 | 工时 |
|---|---|---|---|
| 3.1 | 前端扫描目标管理页（CIDR 增删改） | `frontend/src/views/asset/scan/targets.vue` | 1d |
| 3.2 | 扫描任务详情页（实时进度 + 错误 + 取消/重试） | `frontend/src/views/asset/scan/task-detail.vue` | 1d |
| 3.3 | 增量扫描：F1.3 shadow → 控制面建 `auto-shadow` 任务重扫 | `api/asset_reconciliation.py` 联动 | 0.5d |
| 3.4 | 扫描报告导出（CSV + JSON） | `api/scan.py` | 0.5d |
| 3.5 | 性能压测（100 IP / 1000 port） + 调优 | ops | 1d |
| 3.6 | **收尾（路径 A）**：alembic 合并单 head + 补 `alembic.ini` + 追加 `add_scanner_tables` 迁移 | `alembic/` | 1d |

### Phase 4：高级功能（按需）

| # | 任务 | 工时 |
|---|---|---|
| 4.1 | nmap NSE 脚本（vulners / http-title / ssh-hostkey）填充 `soc_asset_ports.vulnerability` | 2d |
| 4.2 | masscan 集成（>1000 IP 大网段加速） | 3d |
| 4.3 | 跨子网分布式扫描（多容器 + 中心调度） | 5d |
| 4.4 | 扫描结果 AI 解读（接入 GLM） | 3d |

**总工时约 11.3d（约 2.5 周，不含 Phase 3/4）**，控制面与发现/台账解耦逻辑正交，可并行推进。

---

## 十四、测试策略

### 14.1 单元测试（无需网络）

```python
# tests/unit/test_scanner_collector.py
- 用 mock subprocess 返回固定 nmap XML
- 验证 _build_discovery_record / _build_port_record 字段映射
- 验证 nmap 超时 / 失败走 source_health record_failure
```

### 14.2 集成测试（HTTP 路由级 — 遵循 CLAUDE.md 教训）

```python
# tests/integration/test_scanner_e2e.py
- 起 test_app / httpx.AsyncClient
- POST /api/v1/data/sync { source:"scanner", data_type:"discovery", items:[…] }
  → 验证 soc_scan_findings 新增行、source_health scanner:discovery=success
- POST /api/v1/data/sync { source:"scanner", data_type:"port", items:[…] }
  → 验证 soc_asset_ports 新增行、source_health scanner:ports=success
- 触发 F1.3 对账 → 验证 scanner 源 shadow 行（TYPE_SHADOW, asset_id=None）生成
- 触发 F4.2 check_shadow_assets → 验证 scanner 文案推送
- POST /api/v1/scan/findings/{id}/adopt → 验证 soc_assets 新增 + finding_status=adopted
- 端到端控制面：注册扫描器 → 建任务 → 模拟 heartbeat/pull/claim/report → 验证状态流转 + 看门狗离线判定
```

> **CLAUDE.md 教训（:661/:1386）**：service 测过了不代表 endpoint 通。本地端到端一定要用 `httpx.AsyncClient` 或起 uvicorn test_client 跑过路由，不是只调 service 方法。

### 14.3 真链路测试（生产 dry_run / 实扫）

```bash
curl -X POST http://192.168.0.102:8000/api/v1/scan/run \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode":"public","dry_run":true,"target_ids":[1]}'
# 验证：返回 status=pending + task_uuid，但 DB 无变更

curl -X POST .../scan/run -d '{"mode":"public","target_ids":[1],"dry_run":false}'
# 观察：1. task status=running → success
#       2. soc_asset_ports 新增 N 条
#       3. source_health scanner:ports last_success_at 更新
#       4. /data-health 显示 scanner:ports=healthy
```

---

## 十五、风险与缓解

| # | 风险 | 缓解 |
|---|---|---|
| R1 | nmap 容器内发包被 SELinux/AppArmor 拦截 | Dockerfile 加 `--cap-add=NET_RAW NET_ADMIN`；运维验证 `audit2allow` |
| R2 | 内网扫描引发业务中断 | 默认 `--max-rate 100`、`--scan-delay 100ms`；CIDR 需 admin 审批 |
| R3 | 公网扫描引发法律风险 | User-Agent 暴露身份 + 白名单（仅扫自家资产）+ 审计日志 |
| R4 | scanner 覆盖人工设置的 `criticality` | 发现解耦后 scanner **永不写 `soc_assets` 业务字段**；纳管时由请求体显式补 |
| R5 | 大量 PortRecord 撑爆 `soc_asset_ports` | 扫描频率限制 + 定期归档（Phase 4）；当前估算 73×10=730 条，可接受 |
| R6 | scanner 死循环跑挂（nmap 卡死） | 单 IP 300s 超时 + 全网 6h 硬截止 + subprocess kill |
| R7 | F1.3 扩展后 scanner 源 shadow 重复灌 | v1.0 误述「F1.3 按 (run_id, agent_id) 去重」——实测 F1.3 无显式去重，仅靠 `status='pending'` 护栏。v1.1 在「发现维度」分支显式按 `asset_ip` 去重（查 recent shadow 是否已存在） |
| R8 | 菜单树扫描页权限泄漏 | 复用 X1 修复后的 `menu_service.get_menu_tree` 子菜单独立授权 |
| R9 | nmap 版本与镜像兼容 | 锁定 `instrumentisto/nmap:latest` 标签 → 半年一次 review |
| RV-1 | 扫描器伪造心跳伪装在线 | `X-API-Key` 校验 + `api_key_hash` 反查；注册需 admin，禁止零配置接入（NG-5） |
| RV-2 | 认领竞态导致重复执行 | §7.3 `with_for_update()` 行锁 + `pending→running` 原子翻转 |
| RV-3 | 扫描器崩溃遗留 `running` 任务 | 看门狗检测 `running` 超时（> 6h）→ 标 `failed` + 自动重派（§8.1 F-3） |
| RV-4 | 网络抖动致心跳丢失误判离线 | 心跳间隔 30s、离线阈值 90s（3 倍余量）；L1 误判不触发数据丢失（L2 仍有效） |
| RV-5 | auto 路由把所有任务压到一台 | 负载均衡取 `running_tasks` 最小者；`pinned` 可强制指定分散 |
| RV-6 | API Key 泄露被冒用 | 哈希存储 + 可轮换；Key 仅注册时返回一次，落盘用密钥管理 |
| RV-7 | 控制面单点 → 所有扫描器失调度 | 控制面自身高可用沿用 AI-miniSOC 现有部署；扫描器离线时任务留 `pending` 不丢，恢复自动认领 |

---

## 十六、关键决策记录（ADR）

### ADR-1：nmap 单一工具栈
- **选项 A**：仅 nmap（选定 ✅）/ **选项 B**：nmap + masscan
- 决策：仅 nmap。masscan 速度 10x 但探测精度低，发包特征易被 IDS 识别为攻击。
- 后果：单容器内 1000 IP 扫描约需 2h，可接受；未来大网段再评估 masscan。

### ADR-2：影子资产只标记不自动纳管
- **选项 A**：scanner 自动把发现 → `online`（激进）/ **选项 B**：仅标记 + 通知 + 留人工确认（选定 ✅）
- **v1.1 强化**：v1.0 §3.2.3 直接写 `soc_assets` 实际**违背了 ADR-2**；v1.1 通过 `soc_scan_findings` 解耦彻底落实「只标记」，台账写入仅限「一键纳管」。

### ADR-3：扫描频率每日一次
- **选项 A**：每 6h（激进）/ **选项 B**：每日 03:00 / 04:00（选定 ✅，v1.2 落地为固定 24h 间隔对齐该时刻）
- 决策：内网设备 IP 漂移频率约日级别；公网端口变更低频。CPU/网络开销 < 1%。

### ADR-4：触发权限 admin + operator
- **选项 A**：仅 admin / **选项 B**：admin + operator（选定 ✅，与 F1.3 对账一致）

### ADR-5：扫描目标默认合并自动 + 手动
- **选项 A**：仅手动 / **选项 B**：自动从 `soc_assets.network_segment` 汇总 + 手动补充（选定 ✅）
- 后果：部署阶段需 admin 手动加首批 CIDR；运行期自动扩展。

### ADR-6（v1.1 新增）：发现与台账解耦
- **选项 A**：scanner 直接写 `soc_assets`（v1.0，已否）/ **选项 B**：scanner 落独立 `soc_scan_findings`，台账写入仅限「一键纳管」（选定 ✅）
- **决策依据（硬伤 1 修复）**：① 直接写台账会切断 F1.3 shadow 链路；② 直接写台账违背 ADR-2；③ nmap -sn 瞬时/重复命中会污染主资产列表与风险评分。
- **后果**：F1.3 需扩展「发现维度」；F4.2 复用现有过滤 + 补 scanner 文案；纳管为显式、带权限、带审计动作。

### ADR-7（v1.2 新增）：控制面/数据面分离 + 拉模型
- **选项 A**：扫描器内嵌 cron 调度（v1.1 §3.6，已否）/ **选项 B**：AI-miniSOC 中央控制面建任务 + 扫描器拉模型执行（选定 ✅）
- **决策依据**：① 多扫描器场景内嵌调度无法集中编排；② 在线检测必须上提（扫描器框架实测无注册/心跳机制）；③ 拉模型天然穿透 NAT/防火墙且离线任务不丢；④ 与现有采集器「推数据、后端不连采集器」范式一致。
- **后果**：新增 `soc_scanner_agents` + 心跳/看门狗 + 中央调度器；扫描器侧简化为「心跳 + 拉任务 + 执行 + 回推」轻量循环；同步补掉 P4「采集中断无感知」缺口。

### ADR-8（v1.2 新增）：扫描器注册需显式授权
- **选项 A**：扫描器零配置自动接入 / **选项 B**：admin 注册分配 scanner_id + API Key（选定 ✅）
- 决策：避免未授权主机伪装扫描器灌入伪造发现数据（RV-1）；注册时记录能力/子网 + `created_by`，支撑路由与审计。

---

## 十七、关联文档

- [控制面原型](./2026-08-26-control-plane-prototype.html) — 交互式五视图（扫描器/任务/目标/发现/健康）+ 新建任务表单 + 扫描器详情下钻（v1.3 O-4/O-5 已应用：顶部 CSS 变量、mock 数据标注、L3 健康看板）
- [部署架构图](./2026-08-26-deployment-architecture.svg) — 控制面 ↔ 扫描器双向链路
- `docs/design/product-vision-and-technical-roadmap.md` — PRD P3 F1.3 / F1.1 / F4.2 / F3.2
- `docs/design/cmdb-asset-management-asm-recommendations.md` — CMDB 设计
- `docs/design/database-design.md` — `soc_assets` / `soc_asset_ports` / `soc_asset_sources` schema 详解
- `CLAUDE.md` — 关键教训（service 测过了路由未必通 / 独立 session 防 rollback 互杀 / 必须 HTTP 实测）；lifespan scheduler 范式（main.py:51-82）
- `src/collectors/base/collector_framework/sync_client.py` — `MiniSOCClient`（现有 X-API-Key 推送机制，复用其认证模型）
- `src/backend/app/api/deps.py:59` — `require_api_key`（普通采集器鉴权，v1.3 O-1 `require_scanner_api_key` 之镜像）
- `src/backend/app/services/cisa_kev_service.py:223,252` / `alert_group_snapshot_scheduler.py:23,73` — 现有 scheduler 固定秒数间隔范式（v1.3 F-1 依据）

---

## 附录 A：API 请求/响应示例

### POST /api/v1/scan/run（v1.2 §7.2 改写，v1.3 触发表单契约）
```json
{
  "mode": "internal",
  "targets": "192.168.0.0/24",
  "assign_mode": "auto",
  "target_scanner_id": null,
  "schedule": { "type": "now" | "cron", "cron": "0 3 * * *" },
  "nmap_args": null,
  "notify": true
}
```
**Response**：
```json
{ "code": 200, "msg": "success",
  "data": { "task_uuid": "f47ac10b-...", "status": "pending", "mode": "internal",
            "target_count": 1, "dry_run": false, "started_at": "2026-08-26T04:00:00Z" } }
```
→ 建 `soc_scanner_tasks`（状态 `pending`，`run_reason` 立即=`manual`、定时=`scheduled`）→ 目标扫描器下次轮询认领执行。F1.3 触发重扫时 `run_reason=auto-shadow`。

### POST /api/v1/data/sync（scanner → backend，discovery）
```json
{ "source": "scanner", "data_type": "discovery",
  "items": [ { "scan_task_uuid": "f47ac10b-...", "asset_ip": "192.168.0.55",
               "mac_address": "AA:BB:CC:00:11:22", "os_guess": "Linux 5.x",
               "exposure": "internal", "raw_data": { "nmap": { "status": "up", "ports": [] } } } ],
  "metadata": { "duration_ms": 2340 } }
```

### POST /api/v1/data/sync（scanner → backend，port）
```json
{ "source": "scanner", "data_type": "port",
  "items": [ { "asset_ip": "192.168.0.30", "port": 22, "protocol": "tcp", "state": "open",
               "service": "ssh", "version": "OpenSSH 8.4p1 Debian 5+deb11u1",
               "service_banner": "SSH-2.0-OpenSSH_8.4p1 Debian-5+deb11u1", "scan_time": "2026-08-26T03:00:00Z" } ],
  "metadata": { "scan_task_uuid": "f47ac10b-...", "duration_ms": 2340 } }
```

### POST /api/v1/scan/findings/{id}/adopt
```json
{ "asset_name": "内网未命名设备-01", "criticality": "medium", "owner": "ops-team" }
```
**Response**：
```json
{ "code": 200, "msg": "success", "data": { "asset_id": 204, "finding_status": "adopted" } }
```

---

## 附录 B：控制面 ↔ 扫描器交互时序（internal 任务）

```
[控制面]                    [扫描器 192.168.0.45]                [资产/数据]
   |                                |                                |
   |-- 03:00 central_scan_scheduler 建任务(assign_mode=auto) ------->| soc_scanner_tasks: pending
   |                                |                                |
   |                    <-- GET /scan/tasks/pending ----------------|  (每10s轮询)
   |                                |                                |
   |<-- 返回候选任务 ---------------|                                |
   |                                |-- PATCH /scan/tasks/{uuid}/claim (原子)
   |<-- claimed=True + nmap_args ---|                                |
   |                                |-- nmap -sn 192.168.0.0/24 ---->| ARP/ICMP 探测
   |                                |<-- 发现 192.168.0.55 等 ------|
   |<-- POST /data/sync (discovery) |                                |
   |    → soc_scan_findings         |                                |
   |<-- PATCH /scan/tasks/{uuid}/report (success, counts) ----------| soc_scanner_tasks: success
   |                                |                                |
   | (每30s) <-- POST /scan/agents/heartbeat -----------------------| soc_scanner_agents.last_heartbeat 刷新
```

## 附录 C：心跳体示例

```json
POST /api/v1/scan/agents/heartbeat
Headers: { "X-API-Key": "<scanner_key>" }
Body:
{ "scanner_id": "a1b2c3d4-1111-2222-3333-444455556666", "ip": "192.168.0.45",
  "version": "1.2.0", "capabilities": ["internal","public","ports"],
  "reachable_subnets": ["192.168.0.0/24"], "running_tasks": 1 }
```
**Response**：
```json
{ "code": 200, "msg": "success", "data": { "status": "online", "last_heartbeat": "2026-08-26T10:16:12Z" } }
```

## 附录 D：新建扫描任务表单字段与校验规则（字段契约）

> 固化「新建扫描任务」表单契约，供前端实现与 `POST /api/v1/scan/run` 对齐。控制面原型「+ 新建扫描任务」按钮即对应本附录字段。

### D.1 表单字段清单

| # | 字段 | 控件 | 必填 | 映射（列 / 端点） | 说明 |
|---|---|---|---|---|---|
| 1 | 任务名称 | 文本 | 否 | — | 仅展示用 |
| 2 | 扫描模式 `mode` | 单选：internal / public / ports | 是 | `soc_scanner_tasks.mode` | 决定默认 nmap 参数与目标类型 |
| 3 | 扫描目标 `targets` | 文本域（CIDR 或 IP） | 是 | `soc_scan_targets` | auto 路由时按 CIDR 匹配 `reachable_subnets` |
| 4 | 指派方式 `assign_mode` | 单选：auto / pinned | 是 | `assign_mode`（默认 auto） | 控制是否指定执行扫描器 |
| 5 | 目标扫描器 `target_scanner_id` | 下拉（仅 pinned 显示） | pinned 时必填 | `target_scanner_id` | 选项受 `capabilities` + `reachable_subnets` 过滤 |
| 6 | 执行时机 | 单选：立即执行 / 定时 | 是 | `central_scan_scheduler` | 定时填 cron 表达式（仅 UI 表达，后端仍按固定间隔范式建任务） |
| 7 | nmap 参数 `nmap_args` | 文本（高级，默认收起） | 否 | claim 返回 | 留空用模式默认（internal→`-sn`，public→`-sV --top-ports 1000`） |
| 8 | 完成通知 | 开关（默认开） | 否 | F4.2 | 任务结束是否推送 |
| 9 | `run_reason` | 只读 | 系统 | `run_reason` | manual / scheduled / auto-shadow |
| 10 | `capabilities` 快照 | 只读 | 系统 | `capabilities` | 从模式推导 |
| 11 | `scanner_id` | 只读 | 系统 | `scanner_id` | 认领后回写实执行者 |

### D.2 前端校验规则

| 规则 | 触发 | 行为 |
|---|---|---|
| R1 目标格式 | 提交时 | 校验为合法 CIDR（如 `192.168.0.0/24`）或 IPv4；多个逐项校验 |
| R2 指派一致性 | 选 pinned | 强制 `target_scanner_id` 必填，否则禁用提交 |
| R3 子网可达性 | 选 auto + 提交 | 预检是否存在 `reachable_subnets` 覆盖目标 CIDR 且 `status=online` 的扫描器；无则提示「无可用扫描器」并阻断 |
| R4 cron 合法 | 选定时 | 校验 cron 5 段格式（可复用 cisa_kev 既有校验） |
| R5 权限门 | 进入表单 | `require_role("admin","operator")`（ADR-4），无权限不显示「创建」 |

### D.3 提交 → 后端映射

`POST /api/v1/scan/run` 入参（见附录 A）→ 建 `soc_scanner_tasks`（状态 `pending`）→ 目标扫描器下次轮询认领执行（§7.3）。

---

**文档版本**：final（整合 v1.0 + v1.1 + v1.2 + v1.3）
**最后更新**：2026-08-26
**整合来源**：
- v1.0 初稿（方案骨架、采集器设计、调度策略、Phase 计划、风险、ADR-1~5）
- v1.1 修订（发现/台账解耦硬伤1、表改名硬伤2、Alembic 双路径硬伤3、M1–M6/R7 修正、ADR-6）
- v1.2 架构补丁（控制面/数据面分离 ADR-7、拉模型、三层在线检测、soc_scanner_agents、扫描器端点、两调度器、指标体、ADR-8）
- v1.3 评审修复（F-1 固定秒数间隔、F-2 独立 session+dedup+退避、F-3 超时重派、O-1 扫描器鉴权依赖、O-2 L3 回退指标、O-3 compose 片段、O-4 原型 CSS 变量、O-5 原型 mock+L3 看板、M-2 env 示例、M-3 created_by 字段）
**已删除过程稿**：v1.0 / v1.1 / v1.2 / v1.3（合并入本最终稿）
**下次评审**：进入实施；Phase 1 MVP（公网扫描 + 端口落库）完成后回顾 ADR-7 / ADR-8
