# 资产详情页 v2 设计文档

**文档版本**: v1.0
**创建日期**: 2026-06-03
**最后更新**: 2026-06-03
**作者**: Claude
**基础**: `docs/design/asset-detail-optimization-review.md` v1.1
**目标文件**: `src/frontend/src/views/asset/detail/index.vue`

---

## 📋 目录

- [1. 概述](#1-概述)
- [2. 设计目标 & 非目标](#2-设计目标--非目标)
- [3. 已确认的设计决策](#3-已确认的设计决策)
- [4. Tab 顺序与交互模型](#4-tab-顺序与交互模型)
- [5. 整体架构](#5-整体架构)
- [6. 数据模型变更](#6-数据模型变更)
- [7. API 设计](#7-api-设计)
- [8. 前端设计](#8-前端设计)
- [9. Wazuh 同步策略](#9-wazuh-同步策略)
- [10. 实施阶段](#10-实施阶段)
- [11. 测试策略](#11-测试策略)
- [12. 风险与缓解](#12-风险与缓解)
- [13. 验收标准](#13-验收标准)
- [14. 待定项](#14-待定项)
- [15. 版本历史](#15-版本历史)

---

## 1. 概述

### 1.1 背景

基于 2026-06-03 完成的 `asset-detail-optimization-review.md` v1.1 体检报告，本文档将体检中的 P0-P1 建议落地为**可实施的设计**。

### 1.2 文档定位

- **本设计文档** vs **review 文档**：
  - review 文档：识别问题 + 给出方向（已完成）
  - **本文档**：具体架构、数据模型、API 契约、前端组件树、4 阶段实施计划
- **本文档** vs **实施 plan**：
  - 本文档：设计阶段产物，说明"做什么、为什么、怎么做"
  - 实施 plan（后续产出）：按本文档拆分任务，含 TDD 用例、验收脚本

### 1.3 核心设计哲学

**"主机画像优先，事件现场次之"**

| 旧定位 | 新定位 |
|---|---|
| "这个 IP 出事了，过来看" | "这台机器的完整画像" |
| 事件驱动 | 主机驱动 |
| 告警/事件 Tab 占主导 | 摘要卡 + 应用/漏洞/基线 占主导 |
| 告警实时信号是入口 | 主机静态属性是入口，告警是旁支 |

**数据流原则**：UI 永远只读本地 DB（秒开），不直连 Wazuh。Wazuh 是写入源，本地是查询源。

---

## 2. 设计目标 & 非目标

### 2.1 目标

1. ✅ **首屏即结论**：进入详情页 1 秒内，SOC 能回答"这台机器现在安不安全？"
2. ✅ **主机画像完整**：能列出这台机器跑了什么应用、有什么 CVE、开了什么端口、是否符合基线
3. ✅ **告警可下钻**：告警不进 Tab，但摘要卡上能看到，并可一键跳进
4. ✅ **本地秒开**：所有数据本地化（DB 缓存表 + APScheduler 同步），Wazuh 慢/挂不影响详情页
5. ✅ **可观测**：每个同步任务在 `sync_tasks` 表有记录，运维可查
6. ✅ **不破坏现有**：保留端口/标签 Tab 的现有能力，仅做升级

### 2.2 非目标（v2 范围外）

- ❌ 自动化响应剧本（v3+ 再说）
- ❌ 漏洞修复建议生成（AI 集成放到 v3）
- ❌ 多源漏洞库接入（v2 只用 Wazuh vulnerability-detector 自带的 NVD）
- ❌ 威胁情报 IOC 比对（v3+）
- ❌ 工单系统集成（v2 完全下掉事件 Tab）
- ❌ 实时告警推送（WebSocket 留到 v3）
- ❌ 移动端适配（v2 桌面优先）

---

## 3. 已确认的设计决策

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| D1 | Wazuh 应用+漏洞缓存策略 | **DB 缓存表 + 定时同步** | 详情页秒开、可做全公司漏洞排行、跨 worker 共享 |
| D2 | 同步任务调度 | **复用现有 sync_tasks 表** | 统一任务管理、可追踪、复用 `sync_from_wazuh_with_tracking` 模式 |
| D3 | Tab 顺序 | **摘要→应用→漏洞→端口→基线→告警** | "主机画像" 视角，告警是旁支 |
| D4 | 标签 Tab | **下掉**，标签 chip 嵌到基本信息卡 | 标签是上下文属性，不是一个独立模块 |
| D5 | 事件 Tab | **完全下掉** | 与告警/事件列表页功能重叠，详情页不重复 |
| D6 | 基线 Tab 数据源 | **Wazuh SCA** | 零额外配置，Wazuh 默认有 CIS benchmark 套件 |
| D7 | 告警位置 | **只进摘要卡**，不进 Tab | Tab 是静态主机画像，告警是动态信号放在摘要里更合适 |
| D8 | 安全摘要刷新策略 | **进页加载一次**，不自动刷新；提供"刷新"按钮 | 避免轮询，节约 Wazuh 资源 |
| D9 | 告警性能 | **服务端分页 limit=20**，前端不虚拟滚动 | 详情页是单 IP 上下文，20 条足够呈现 |
| D10 | 数据分类字段 | **可选**，不强制 | 不阻挡老资产录入；v2 上线后再加业务约束 |
| D11 | 标签字典化方案 | **复用 soc_dicts**，dict_type='asset_tag_key_*' | 与现有字典系统统一，零新表 |
| D12 | 漏洞补丁状态 | **Wazuh 提供的 patched/unpatched 状态原样展示** | 不二次加工，避免误导 |

---

## 4. Tab 顺序与交互模型

### 4.1 最终 Tab 结构

```
┌────────────────────────────────────────────────────────────┐
│ [基本信息卡] IP / 名称 / 状态 / 标签 chip / 描述 / 负责人   │  ← 保留并升级
├────────────────────────────────────────────────────────────┤
│ [安全摘要卡] 6 个 MetricCard 横排                            │  ← 新增
│   24h告警 | 高危CVE | 开放端口 | 应用数 | SCA合规率 | 在线   │
├────────────────────────────────────────────────────────────┤
│ [Tab 栏]                                                     │
│   ① 应用清单   ② 漏洞   ③ 端口   ④ 基线   ⑤ 告警            │  ← 5 个 Tab
└────────────────────────────────────────────────────────────┘
```

### 4.2 Tab 默认进入

**默认进 "应用清单"**（第一个数据 Tab），不是"摘要"——因为摘要卡已经常驻在 Tab 上方了。

### 4.3 标签位置

标签从 Tab 下掉，移到基本信息卡里以 ElTag chip 横向展示：

```vue
<ElDescriptionsItem label="标签">
  <ElTag v-for="tag in assetTags" :key="tag.id" type="info" effect="light" class="mr-1">
    {{ tag.tag_key }}: {{ tag.tag_value }}
  </ElTag>
  <ElButton text type="primary" @click="tagDialogVisible = true">
    <ElIcon><Edit /></ElIcon>管理
  </ElButton>
</ElDescriptionsItem>
```

### 4.4 告警与摘要的交互

摘要卡里的"24h 告警" MetricCard 是**可点击**的：
- 悬停：`cursor: pointer`
- 点击：路由到告警 Tab
- 副标：右下方小字"查看告警 →"提示

这样告警在视觉上"在"摘要卡里，但行为上"能下钻"。

---

## 5. 整体架构

### 5.1 数据流图

```
┌──────────────────────────────────────────────────────────────┐
│           Frontend: detail/index.vue                         │
│  ┌──────────┬──────────┬──────────┬──────────┬──────────┐    │
│  │摘要卡(常驻)│ 应用 Tab │ 漏洞 Tab │ 端口 Tab │ 基线 Tab │告警 Tab
│  └────┬─────┴────┬─────┴────┬─────┴────┬─────┴────┬─────┘    │
│       │          │          │          │          │          │
│  ┌────▼──────────▼──────────▼──────────▼──────────▼─────┐    │
│  │  src/frontend/src/api/                              │    │
│  │   asset.ts (现有) | alert.ts (新增) | wazuh.ts (新增) │    │
│  └────┬──────────┬──────────┬──────────┬──────────┬─────┘    │
└───────┼──────────┼──────────┼──────────┼──────────┼──────────┘
        │          │          │          │          │
        ▼          ▼          ▼          ▼          ▼
┌──────────────────────────────────────────────────────────────┐
│                  FastAPI Backend                              │
│                                                                │
│  /assets/{id}/summary (新)                                    │
│  /assets/{id}/ports (现有,加 vulnerability 字段展示)         │
│  /wazuh/agents/{id}/packages (新,读本地缓存表)              │
│  /wazuh/agents/{id}/vulnerabilities (新,读本地缓存表)        │
│  /wazuh/agents/{id}/sca (新,读本地缓存表)                    │
│  /alerts/?ip= (现有,前端接入)                                 │
│  /wazuh/sync/{type} (新,触发同步)                             │
│  /wazuh/sync-tasks (新,查询任务状态)                          │
│                                                                │
│  ┌──────────────────────────────────────────────────┐        │
│  │  WazuhSyncService (新)                            │        │
│  │  - sync_packages() → 写 soc_wazuh_packages        │        │
│  │  - sync_vulnerabilities() → 写 soc_wazuh_vulns   │        │
│  │  - sync_sca() → 写 soc_wazuh_sca_results          │        │
│  │  - 每个都通过 sync_tasks 追踪                     │        │
│  │  - APScheduler 1h 自动触发                        │        │
│  └──────────────────────────────────────────────────┘        │
│         │                                                     │
│         ▼                                                     │
│  ┌──────────────────────────────────────────────────┐        │
│  │  WazuhClient (扩展)                                │        │
│  │  + get_agent_packages(agent_id, limit)            │        │
│  │  + get_agent_vulnerabilities(agent_id, severity)  │        │
│  │  + get_agent_sca(agent_id)                        │        │
│  └──────────────────────────────────────────────────┘        │
│         │                                                     │
│         ▼                                                     │
│  ┌──────────────────┐   ┌────────────────────┐              │
│  │  Wazuh Server     │   │   OpenSearch       │              │
│  │  /syscollector/   │   │  (告警已用)         │              │
│  │  /vulnerability/  │   │                    │              │
│  │  /sca/            │   │                    │              │
│  └──────────────────┘   └────────────────────┘              │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 同步触发机制

```
┌─────────────────────────────────────────────────────────────┐
│  APScheduler (lifespan 启动)                                │
│  ┌──────────────────┬──────────────────┬──────────────┐    │
│  │ CronTrigger(1h)  │ CronTrigger(1h)  │ CronTrigger  │    │
│  │ sync_packages()  │ sync_vulns()     │ sync_sca()   │    │
│  │                  │                  │              │    │
│  │ 遍历所有有       │ 同左             │ 同左          │    │
│  │ wazuh_agent_id   │                  │              │    │
│  │ 的资产,逐个      │                  │              │    │
│  │ 调 Wazuh API     │                  │              │    │
│  │ 写本地缓存表     │                  │              │    │
│  │ 写 sync_tasks    │                  │              │    │
│  └──────────────────┴──────────────────┴──────────────┘    │
└─────────────────────────────────────────────────────────────┘
       │                              │
       │ 1h 自动                       │ 手动触发 (POST /wazuh/sync/...)
       ▼                              ▼
   ┌──────────────────────────────────────────┐
   │  sync_tasks 表记录 (sync_type 区分)       │
   │  - 'wazuh_packages'                      │
   │  - 'wazuh_vulnerabilities'               │
   │  - 'wazuh_sca'                           │
   │  - 'manual' (保留原有用法)               │
   └──────────────────────────────────────────┘
```

**多 worker 部署注意**：APScheduler 在每个 worker 进程都会启动，1h 同步会重复执行 N 次。**v2 接受这个限制**（每 worker 独立任务，DB UNIQUE 约束去重），在 v3 引入 Redis 分布式锁或选 leader。

---

## 6. 数据模型变更

### 6.1 新增表（3 张）

#### 6.1.1 `soc_wazuh_packages` — Wazuh 应用缓存表

```sql
CREATE TABLE soc_wazuh_packages (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id        uuid NOT NULL REFERENCES soc_assets(id) ON DELETE CASCADE,
    name            varchar(255) NOT NULL,
    version         varchar(100),
    vendor          varchar(255),
    architecture    varchar(50),
    scan_time       timestamptz NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_wazuh_package UNIQUE (asset_id, name, version)
);

CREATE INDEX idx_wazuh_packages_asset ON soc_wazuh_packages(asset_id);
CREATE INDEX idx_wazuh_packages_name ON soc_wazuh_packages(name);
```

#### 6.1.2 `soc_wazuh_vulnerabilities` — Wazuh 漏洞缓存表

```sql
CREATE TABLE soc_wazuh_vulnerabilities (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id          uuid NOT NULL REFERENCES soc_assets(id) ON DELETE CASCADE,
    cve_id            varchar(30) NOT NULL,            -- e.g. 'CVE-2021-23017'
    severity          varchar(20) NOT NULL,            -- critical / high / medium / low
    cvss3_score       numeric(4, 1),
    package_name      varchar(255) NOT NULL,
    package_version   varchar(100),
    fix_version       varchar(100),                   -- 修复版本(可能为空)
    status            varchar(20) NOT NULL DEFAULT 'unpatched',  -- Wazuh: patched / unpatched
    title             varchar(500),                   -- 漏洞标题
    scan_time         timestamptz NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_wazuh_vuln UNIQUE (asset_id, cve_id),
    CONSTRAINT soc_wazuh_vulns_severity_check CHECK (severity IN ('critical','high','medium','low')),
    CONSTRAINT soc_wazuh_vulns_status_check CHECK (status IN ('patched','unpatched'))
);

CREATE INDEX idx_wazuh_vulns_asset ON soc_wazuh_vulnerabilities(asset_id);
CREATE INDEX idx_wazuh_vulns_severity ON soc_wazuh_vulnerabilities(severity, cvss3_score DESC);
CREATE INDEX idx_wazuh_vulns_cve ON soc_wazuh_vulnerabilities(cve_id);
```

#### 6.1.3 `soc_wazuh_sca_results` — Wazuh SCA 合规检查结果

```sql
CREATE TABLE soc_wazuh_sca_results (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id        uuid NOT NULL REFERENCES soc_assets(id) ON DELETE CASCADE,
    check_id        varchar(100) NOT NULL,           -- Wazuh SCA check 唯一 ID
    policy_id       varchar(100) NOT NULL,           -- e.g. 'cis_ubuntu20_04'
    policy_name     varchar(255),                    -- e.g. 'CIS Ubuntu Linux 20.04'
    title           varchar(500),
    description     text,
    rationale       text,
    result          varchar(20) NOT NULL,            -- passed / failed / not_applicable
    compliance      jsonb,                           -- [{"standard":"cis","version":"1.0","control":"1.1.1"}]
    scan_time       timestamptz NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT uq_wazuh_sca UNIQUE (asset_id, check_id),
    CONSTRAINT soc_wazuh_sca_result_check CHECK (result IN ('passed','failed','not_applicable'))
);

CREATE INDEX idx_wazuh_sca_asset_result ON soc_wazuh_sca_results(asset_id, result);
CREATE INDEX idx_wazuh_sca_policy ON soc_wazuh_sca_results(policy_id);
```

### 6.2 新增列（2 个，扩展 `soc_assets`）

| 字段 | 类型 | 约束 | 默认 | 说明 |
|---|---|---|---|---|
| `data_classification` | VARCHAR(20) | CHECK in 'public','internal','confidential','secret' | 'internal' | 数据敏感度（合规字段） |
| `owner_contact` | VARCHAR(50) | NULL | NULL | 负责人联系电话 |

### 6.3 现有表说明

- `soc_asset_ports.vulnerability` 已存在，**无需新增**——只在前端展示
- `soc_assets.wazuh_agent_id` 已存在，**无需新增**——同步任务按此 join
- `sync_tasks` 已存在，**复用** `sync_type` 字段区分（新增枚举值）

### 6.4 数据保留策略

- 3 张缓存表**不做物理删除**，每次同步全量 upsert（资产删了 → CASCADE）
- `soc_wazuh_vulnerabilities.scan_time` 保留最后一次扫描时间，用于"扫描新鲜度"展示
- 不在 v2 范围内做历史扫描归档（v3+ 再说）

---

## 7. API 设计

所有 API 走 `/api/v1/` 前缀，遵循现有 `{code, msg, data}` 响应包装。

### 7.1 新增：安全摘要聚合接口

```http
GET /api/v1/assets/{id}/summary
```

**响应**：
```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "asset_id": "uuid",
    "online_status": "online",                   // online/offline/unknown
    "alert_24h": 12,                              // 近 24h 告警数
    "alert_critical_24h": 2,                      // 近 24h 高危 (level>=12) 告警数
    "open_incidents": 1,                          // 未关闭事件数
    "vuln_critical": 3,                           // critical 漏洞数
    "vuln_high": 8,                               // high 漏洞数
    "vuln_total": 24,                             // 全部未修复漏洞数
    "open_ports": 18,                             // 开放端口数
    "high_risk_ports": 2,                         // 高危端口数 (22/3389/445/3306/1433/2375/9200/...)
    "applications": 437,                          // 应用数
    "sca_pass_rate": 0.78,                        // SCA 通过率 (0-1)
    "sca_total": 245,                             // SCA 检查项总数
    "sca_failed": 54,                             // SCA 失败项数
    "last_port_scan": "2026-06-03T10:30:00Z",     // 端口扫描时间
    "last_vuln_scan": "2026-06-03T08:15:00Z",     // 漏洞扫描时间
    "last_sca_scan": "2026-06-02T22:00:00Z",      // SCA 扫描时间
    "data_classification": "internal",            // 数据分类
    "tags": [
      {"key": "environment", "value": "production"},
      {"key": "business_system", "value": "hr-system"}
    ]
  }
}
```

**实现要点**：
- 单次 DB 查询，多个 `COUNT/CASE WHEN` 聚合
- 告警数走 OpenSearch（与现有 `/alerts/?ip=` 复用）
- 失败兜底：Wazuh 缓存表无数据时返回 `vuln_critical=0, sca_pass_rate=null`，前端显示 "暂无数据"

### 7.2 新增：Wazuh 数据查询接口（3 个，读本地缓存表）

```http
GET /api/v1/wazuh/agents/{agent_id}/packages?limit=500&offset=0
GET /api/v1/wazuh/agents/{agent_id}/vulnerabilities?severity=critical,high&limit=500
GET /api/v1/wazuh/agents/{agent_id}/sca?result=failed&policy_id=cis_ubuntu20_04&limit=500
```

**packages 响应**：
```json
{
  "code": 200,
  "data": {
    "items": [
      {"id":"uuid","name":"openssl","version":"1.1.1f-1ubuntu2","vendor":"Ubuntu","architecture":"amd64","scan_time":"2026-06-03T08:00:00Z"}
    ],
    "total": 437
  }
}
```

**vulnerabilities 响应**：
```json
{
  "code": 200,
  "data": {
    "items": [
      {"id":"uuid","cve_id":"CVE-2021-23017","severity":"high","cvss3_score":7.7,"package_name":"openssl","package_version":"1.1.1f","fix_version":"1.1.1i","status":"unpatched","title":"...","scan_time":"..."}
    ],
    "total": 24
  }
}
```

**sca 响应**：
```json
{
  "code": 200,
  "data": {
    "items": [
      {"id":"uuid","check_id":"1100","policy_id":"cis_ubuntu20_04","title":"Ensure...","result":"failed","compliance":[{"standard":"cis","version":"1.0","control":"1.1.1"}],"scan_time":"..."}
    ],
    "total": 54
  }
}
```

### 7.3 新增：告警 Tab 接入（前端补封装）

`src/frontend/src/api/alert.ts`（新增）：
```typescript
export const getAlertsByIp = (ip: string, params?: { hours?: number; level?: number; skip?: number; limit?: number }) => {...}
export const getAlertStatistics = (params?: { hours?: number; ip?: string }) => {...}
```

后端 `/api/v1/alerts/?ip=` **已存在**，无需新增。

### 7.4 新增：手动同步触发接口

```http
POST /api/v1/wazuh/sync/packages
POST /api/v1/wazuh/sync/vulnerabilities
POST /api/v1/wazuh/sync/sca
```

**响应**：
```json
{
  "code": 200,
  "data": {
    "task_id": "uuid",
    "status": "running",
    "estimated_assets": 87
  }
}
```

**实现要点**：
- 创建 SyncTask 记录（status=running）
- 同步执行（前端可轮询 task_id 看完成情况）
- 失败时 status=failed，error_message 记录原因
- **同步触发不阻塞响应**：v2 直接同步执行（资产少，<10s 完成）；v3 改成 FastAPI BackgroundTasks

### 7.5 新增：同步任务查询

```http
GET /api/v1/wazuh/sync-tasks?sync_type=wazuh_packages&limit=10
```

复用 `sync_tasks` 表，前端可展示"上次同步时间 / 状态 / 失败原因"。

---

## 8. 前端设计

### 8.1 组件树

```
views/asset/detail/index.vue (主页面,~700 行)
├── ElCard (基本信息卡,保留+升级)
│   ├── ElDescriptions (2 列)
│   └── 标签 chip + 管理按钮 (从原 Tab 移过来)
│
├── ElCard (安全摘要卡,新增)
│   └── <MetricCard> x 6
│       ├── 24h 告警 (可点击 → 告警 Tab)
│       ├── 高危 CVE (可点击 → 漏洞 Tab)
│       ├── 开放端口 (可点击 → 端口 Tab)
│       ├── 应用数 (可点击 → 应用 Tab)
│       ├── SCA 合规率 (可点击 → 基线 Tab)
│       └── 在线状态 (只读)
│
├── ElTabs (5 个 Tab,顺序: 应用→漏洞→端口→基线→告警)
│   ├── ElTabPane #1: 应用清单
│   │   ├── ElTable (列:name | version | vendor | arch | 关联漏洞数 | 扫描时间)
│   │   └── 筛选器: name 搜索 / 厂商 / 架构
│   │
│   ├── ElTabPane #2: 漏洞列表
│   │   ├── 头部: Critical: 0 | High: 0 | Medium: 0 | Low: 0 计数条
│   │   ├── ElTable (列:CVE | 严重性 | CVSS3 | 影响包 | 当前版本 | 修复版本 | 状态)
│   │   └── 筛选器: 严重性多选 / 状态(已修复/未修复)
│   │
│   ├── ElTabPane #3: 端口管理 (现有,增强)
│   │   ├── ElTable (列:端口 | 协议 | 状态 | 服务 | 版本 | 风险等级 | 漏洞 | 扫描时间)
│   │   ├── 高危端口库: 前端常量 HIGH_RISK_PORTS
│   │   ├── 命中高危的端口行 ElTag danger 标记
│   │   └── vulnerability 字段逗号拆成多个 ElTag
│   │
│   ├── ElTabPane #4: 基线 (Wazuh SCA)
│   │   ├── 头部: 政策名 + 通过/失败/不适用 计数 + 通过率
│   │   ├── ElTable (列:Check ID | 标题 | 标准 | 控制项 | 结果)
│   │   └── 筛选器: result / policy_id
│   │
│   └── ElTabPane #5: 告警 (从原"关联事件"改名 + 接入 Wazuh alerts)
│       └── ElTable (列:时间 | 等级 | 规则描述 | Agent | 操作)
│
├── ElDialog (端口弹窗,现有)
├── ElDialog (标签弹窗,现有,但改为从基本信息卡触发)
└── (移除) 事件 Tab + 标签 Tab
```

### 8.2 新增/修改的文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `src/frontend/src/views/asset/detail/index.vue` | **重写** | 600+ 行 → 800+ 行；Tab 顺序、摘要卡、标签 chip、Tab 内容升级 |
| `src/frontend/src/api/alert.ts` | **新增** | 告警 API 封装（`getAlertsByIp`, `getAlertStatistics`） |
| `src/frontend/src/api/wazuh.ts` | **新增** | Wazuh 数据查询 + 同步触发 |
| `src/frontend/src/types/api/api.d.ts` | **修改** | 加 `WazuhPackage`, `WazuhVulnerability`, `WazuhScaResult`, `AssetSummary` 类型 |
| `src/frontend/src/api/asset.ts` | **修改** | 加 `getAssetSummary(id)` |
| `src/frontend/src/views/asset/detail/components/MetricCard.vue` | **新增** | 摘要卡内的可点击小卡片（~80 行） |
| `src/frontend/src/composables/useRelativeTime.ts` | **新增** | 时间格式化工具（< 1h="刚刚", >= 30d="过期"） |
| `src/frontend/src/constants/highRiskPorts.ts` | **新增** | 高危端口常量库 |

### 8.3 后端新增/修改的文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `src/backend/app/models/wazuh_package.py` | **新增** | SQLAlchemy 模型 |
| `src/backend/app/models/wazuh_vulnerability.py` | **新增** | SQLAlchemy 模型 |
| `src/backend/app/models/wazuh_sca.py` | **新增** | SQLAlchemy 模型 |
| `src/backend/app/models/__init__.py` | **修改** | 注册 3 个新模型 |
| `src/backend/app/models/asset.py` | **修改** | 加 `data_classification` + `owner_contact` 字段 |
| `src/backend/app/schemas/asset.py` | **修改** | Schema 加 2 个字段 |
| `src/backend/app/schemas/wazuh.py` | **新增** | Pydantic Schema（3 个） |
| `src/backend/app/services/wazuh_client.py` | **修改** | 加 3 个新方法（packages/vulns/sca） |
| `src/backend/app/services/wazuh_sync.py` | **新增** | 同步服务（DB 缓存 + SyncTask 追踪） |
| `src/backend/app/services/asset_summary.py` | **新增** | 摘要聚合服务 |
| `src/backend/app/api/assets.py` | **修改** | 加 `GET /{id}/summary` 端点 |
| `src/backend/app/api/wazuh.py` | **新增** | 6 个端点（3 查询 + 3 同步触发 + 1 任务查询） |
| `src/backend/main.py` | **修改** | lifespan 启动 APScheduler |
| `src/backend/alembic/versions/xxxx_add_wazuh_cache_tables.py` | **新增** | Alembic 迁移（3 张新表 + 2 个新列） |
| `src/backend/app/core/config.py` | **修改** | 加 `WAZUH_SYNC_INTERVAL_HOURS=1` 配置 |
| `scripts/database/init_soc_assets.sql` 等 5 个 DDL | **修改** | 新装环境同步 DDL |

### 8.4 关键 UI 模式

#### 8.4.1 摘要卡 MetricCard

```vue
<MetricCard
  label="24h 告警"
  :value="summary.alert_24h"
  type="danger"
  :clickable="summary.alert_24h > 0"
  @click="activeTab = 'alerts'"
  :sub-label="summary.alert_critical_24h > 0 ? `高危 ${summary.alert_critical_24h}` : '无高危'"
/>
```

#### 8.4.2 漏洞 Tab 头部计数条

```vue
<div class="vuln-summary-bar">
  <ElTag type="danger" effect="dark">Critical: {{ counts.critical }}</ElTag>
  <ElTag type="warning" effect="light">High: {{ counts.high }}</ElTag>
  <ElTag type="info" effect="light">Medium: {{ counts.medium }}</ElTag>
  <ElTag type="info" effect="plain">Low: {{ counts.low }}</ElTag>
</div>
```

#### 8.4.3 高危端口行高亮

```typescript
const HIGH_RISK_PORTS: Record<number, { risk: 'critical' | 'high' | 'medium'; reason: string }> = {
  22: { risk: 'high', reason: 'SSH 远程管理' },
  3389: { risk: 'high', reason: 'RDP 远程桌面' },
  445: { risk: 'high', reason: 'SMB 文件共享' },
  3306: { risk: 'high', reason: 'MySQL 数据库' },
  // ... 详见 src/frontend/src/constants/highRiskPorts.ts
}

// 行 formatter:
formatter: (row) => HIGH_RISK_PORTS[row.port]
  ? h('ElTag', { type: 'danger', effect: 'dark' }, HIGH_RISK_PORTS[row.port].reason)
  : '--'
```

#### 8.4.4 漏洞补丁状态

```typescript
// 直接用 Wazuh 的 patched / unpatched
formatter: (row) => h('ElTag', {
  type: row.status === 'unpatched' ? 'danger' : 'success',
  effect: 'light'
}, { default: () => row.status === 'unpatched' ? '未修复' : '已修复' })
```

---

## 9. Wazuh 同步策略

### 9.1 同步触发矩阵

| 触发源 | 频率 | 范围 | 实现 |
|---|---|---|---|
| APScheduler 自动 | 1h | 全量（有 wazuh_agent_id 的所有资产） | `main.py` lifespan 启动，cron 触发 |
| 手动 API 触发 | 按需 | 全量 | `POST /api/v1/wazuh/sync/{type}` |
| 详情页"刷新"按钮 | 按需 | 单资产 | 触发该资产对应的同步（**v3 再加**） |

### 9.2 同步逻辑（以 packages 为例）

```python
class WazuhSyncService:
    def sync_packages(self, sync_type: str = "wazuh_packages") -> SyncTask:
        task = SyncTask(sync_type=sync_type, status="running", started_at=now())
        self.db.add(task)
        self.db.commit()

        try:
            # 1. 取所有有 wazuh_agent_id 的资产
            assets = self.db.query(Asset).filter(Asset.wazuh_agent_id.isnot(None)).all()
            task.total_count = len(assets)
            self.db.commit()

            # 2. 逐个资产同步
            for asset in assets:
                try:
                    packages = wazuh_client.get_agent_packages(asset.wazuh_agent_id)
                    self._upsert_packages(asset.id, packages)
                    task.updated_count += 1
                except Exception as e:
                    task.failed_count += 1
                    logger.error(f"资产 {asset.id} 包同步失败: {e}")

            task.status = "completed"
        except Exception as e:
            task.status = "failed"
            task.error_message = str(e)
        finally:
            task.completed_at = now()
            self.db.commit()
        return task

    def _upsert_packages(self, asset_id: str, packages: List[dict]) -> None:
        """PostgreSQL UPSERT: 删旧+插新 或 ON CONFLICT DO UPDATE"""
        # 方案 A: 全删全插(简单,但事务大)
        self.db.query(WazuhPackage).filter(WazuhPackage.asset_id == asset_id).delete()
        for pkg in packages:
            self.db.add(WazuhPackage(asset_id=asset_id, **pkg))
        # 方案 B: ON CONFLICT(UNIQUE) DO UPDATE(更快,v2 选用此)
```

### 9.3 性能与限流

| 资产数 | Wazuh API 延迟 | 同步总耗时 | 备注 |
|---|---|---|---|
| 10 | 200ms | 2s | 可接受 |
| 50 | 200ms | 10s | 接近前端超时 |
| 100+ | 200ms | 20s+ | **需并发** |

**v2 限制**：< 50 资产的中小团队够用，串行同步
**v3 改进**：asyncio.gather + httpx.AsyncClient 并发 + 限流器

### 9.4 Wazuh SCA 启用检查

Wazuh SCA 模块默认在 Wazuh 4.x 中**已启用**，但每个 agent 需要：
- `agent.conf` 中启用 `sca` 模块
- 至少有一个 policy 适用该 OS

**降级策略**：如果某资产 `get_agent_sca()` 返回空 → 摘要卡 SCA 合规率显示 "—"，Tab 内显示 "该资产无 SCA 数据（可能 Wazuh SCA 未启用）"。

---

## 10. 实施阶段

### 10.1 总览（4 阶段，约 2 周）

```
┌──────────────────────────────────────────────────────────────┐
│ Phase 1 (P0, 1.5 天)        │ 摘要卡 + 告警接入 + 端口增强     │
├──────────────────────────────────────────────────────────────┤
│ Phase 2 (P0, 3 天)          │ Wazuh 客户端 + 缓存表 + 同步    │
├──────────────────────────────────────────────────────────────┤
│ Phase 3 (P0, 1.5 天)        │ 应用 Tab + 漏洞 Tab              │
├──────────────────────────────────────────────────────────────┤
│ Phase 4 (P1, 1.5 天)        │ 基线 Tab + 标签字典化 + 收尾    │
└──────────────────────────────────────────────────────────────┘
```

### 10.2 Phase 1：摘要卡 + 告警 + 端口增强

**目标**：详情页首屏即结论、告警可下钻、端口有风险标

**任务**：
1. 后端：
   - `asset_summary.py` 服务 + `GET /api/v1/assets/{id}/summary` 端点
   - 暂用现有数据（告警/事件/端口/标签），不需要 Wazuh 缓存表
   - `soc_assets` 加 `data_classification` + `owner_contact` 列 + Alembic 迁移
2. 前端：
   - 详情页基本信息卡加标签 chip
   - 新增 `MetricCard.vue` 组件
   - 详情页 Tab 上方加摘要卡
   - 新增 `api/alert.ts` 封装
   - 详情页告警 Tab 接入（5 个 Tab 中的最后一个）
   - 端口 Tab 加 `vulnerability` 字段展示 + 高危端口库 + 风险标红
   - `highRiskPorts.ts` 常量
3. 收尾：
   - 移除原"关联事件" Tab 全部代码
   - 移除原"标签管理" Tab 入口（保留标签弹窗，从基本信息卡触发）

**验收**：
- 详情页打开 1s 内看到摘要卡 6 个指标
- 告警 Tab 显示实际 Wazuh 告警（按 IP 过滤）
- 端口表 22 端口行红色高危标

### 10.3 Phase 2：Wazuh 集成

**目标**：本地缓存 Wazuh 应用+漏洞数据，秒开

**任务**：
1. 后端：
   - 3 张新表 SQLAlchemy 模型 + Alembic 迁移
   - `wazuh_client.py` 加 3 个新方法（packages/vulns/sca）
   - `wazuh_sync.py` 服务 + `sync_tasks` 追踪
   - `api/wazuh.py` 6 个新端点（3 查询 + 3 同步）
   - `main.py` lifespan 启动 APScheduler（1h cron × 3 任务）
   - `config.py` 加 `WAZUH_SYNC_INTERVAL_HOURS=1` 配置
2. 前端：
   - `api/wazuh.ts` 封装（3 个查询 + 3 个同步 + 任务查询）
   - `types/api/api.d.ts` 加 3 个 Wazuh 类型
3. 验证：
   - 手动 `POST /api/v1/wazuh/sync/packages` 触发
   - 查 `sync_tasks` 表确认有记录
   - 查 `soc_wazuh_packages` 表有数据
   - 1h 后自动同步生效

**验收**：
- `curl /api/v1/wazuh/agents/{id}/packages` 返回本地数据
- `soc_wazuh_packages` 表有数据，`updated_at` 1h 内
- Wazuh API 关闭后，详情页仍能查询（秒开）

### 10.4 Phase 3：应用 Tab + 漏洞 Tab

**目标**：可查看主机应用清单和漏洞

**任务**：
1. 前端：
   - 详情页加"应用清单" Tab（第一个 Tab）
     - 表格列：name | version | vendor | architecture | 扫描时间
     - 搜索 + 分页
   - 详情页加"漏洞" Tab（第二个 Tab）
     - 头部计数条：Critical / High / Medium / Low
     - 表格列：CVE | 严重性 | CVSS3 | 影响包 | 当前版本 | 修复版本 | 状态
     - 严重性多选筛选 + 状态筛选
2. 数据关联：
   - 应用 Tab 显示"关联漏洞数"列（JOIN `soc_wazuh_vulnerabilities`）
   - 漏洞 Tab 点击 CVE 可跳到 NVD（可选，v2 不做）

**验收**：
- 应用 Tab 显示该资产的所有已装软件
- 漏洞 Tab 按严重性排序显示
- 头部计数与表格一致

### 10.5 Phase 4：基线 Tab + 标签字典化

**目标**：SCA 合规展示 + 标签键字典驱动

**任务**：
1. 前端：
   - 详情页加"基线" Tab
     - 头部：政策名 + 通过/失败计数 + 通过率
     - 表格列：Check ID | 标题 | 标准 | 控制项 | 结果
   - 标签管理弹窗改字典驱动
     - 从 `soc_dicts` 读 `dict_type='asset_tag_key_*'`
     - 可选 value 也用字典
2. 后端：
   - 字典 seed：插入常用标签键（environment, business_system, location, team, data_classification）
3. 收尾：
   - 全文搜索 "tab" 相关代码 review
   - 5 个 Tab 顺序确认

**验收**：
- 基线 Tab 显示该资产的 SCA 检查结果
- 添加标签时下拉选项从字典来（无硬编码）
- 改字典后前端 label 实时生效

---

## 11. 测试策略

### 11.1 后端

| 类型 | 覆盖 | 工具 |
|---|---|---|
| 单元 | `wazuh_sync.py`, `asset_summary.py`, `wazuh_client.py` 新方法 | pytest + unittest.mock |
| 集成 | 3 张新表 CRUD / Alembic 迁移 / API 端点 200/4xx 响应 | pytest + httpx + 测试库 |
| 端到端 | 同步任务完整流程（创建 → 运行 → 写表 → 完成任务） | pytest + 测试库 |

**目标覆盖率**：> 80%（遵循 common/testing.md）

### 11.2 前端

| 类型 | 覆盖 | 工具 |
|---|---|---|
| 单元 | `useRelativeTime`, `highRiskPorts` 匹配函数 | vitest |
| 组件 | `MetricCard.vue` 渲染 + 点击事件 | vitest + @vue/test-utils |
| 视觉 | 5 个 Tab 切换状态、摘要卡布局 | Playwright screenshot |
| E2E | 进详情页 → 看摘要卡 → 点告警 → 看到告警列表 | Playwright |

### 11.3 手动验收

每个 Phase 完成后，需要在 staging 跑：
- 详情页加载性能（< 2s）
- 同步任务在 sync_tasks 表有记录
- 缓存表数据与 Wazuh API 一致（抽样 3 个资产对比）

---

## 12. 风险与缓解

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | Wazuh SCA 模块未启用 | 中 | 降级显示"该资产无 SCA 数据"，日志 warn |
| R2 | Wazuh vulnerability-detector 无 NVD 订阅 | 中 | 摘要卡 CVE 计数显示 0 + Tab 提示"暂无漏洞数据" |
| R3 | Wazuh API 慢导致同步超时 | 中 | 单资产 try-except 隔离失败，全局不中断 |
| R4 | APScheduler 多 worker 重复执行 | 中 | v2 接受（DB UNIQUE 去重），v3 加分布式锁 |
| R5 | 100+ 资产同步耗时长（>30s） | 低 | v2 限 50 资产内；v3 改并发 |
| R6 | 漏洞表数据膨胀（千条/资产） | 低 | UNIQUE(asset_id, cve_id) + 索引 + 分页 |
| R7 | 同步时 DB 锁竞争 | 低 | 同步走单独 session，写完 commit 立即释放 |
| R8 | 用户改 dict 后前端缓存 stale | 低 | dictStore 已有 `refreshType()`，CRUD 后调用 |
| R9 | `data_classification` 老资产无值 | 低 | 迁移时 `DEFAULT 'internal'`，前端默认显示 |
| R10 | 标签 dict 化后，存量硬编码标签怎么办 | 中 | 阶段 4 提供数据迁移脚本（按 tag_key → dict_type 映射） |

---

## 13. 验收标准

### 13.1 Phase 1 验收（1.5 天）

- [ ] 详情页打开 1s 内显示 6 个摘要指标
- [ ] 摘要卡"24h 告警"可点击跳到告警 Tab
- [ ] 告警 Tab 显示真实 Wazuh 告警（按 IP 过滤）
- [ ] 端口表 22/3389 端口行红色高危标
- [ ] 端口表 `vulnerability` 字段以 ElTag 列表展示
- [ ] 基本信息卡显示所有标签 + 管理按钮
- [ ] 原"关联事件" Tab 完全移除
- [ ] 49 个 in-process 测试全绿
- [ ] 详情页 543 → 700-800 行

### 13.2 Phase 2 验收（3 天）

- [ ] Alembic 迁移成功，3 张新表 + 2 个新列创建
- [ ] `curl POST /api/v1/wazuh/sync/packages` 触发后 sync_tasks 有记录
- [ ] `soc_wazuh_packages` 表有数据（抽样 1 资产验证）
- [ ] 1h 后自动同步生效（看 `updated_at`）
- [ ] Wazuh API 关闭后，`GET /api/v1/wazuh/agents/{id}/packages` 仍返回本地数据
- [ ] 同步服务 80%+ 单元测试覆盖

### 13.3 Phase 3 验收（1.5 天）

- [ ] 应用 Tab 显示资产的所有已装软件（至少 1 个真实资产验证）
- [ ] 漏洞 Tab 按严重性排序，header 计数与表格一致
- [ ] 应用名搜索过滤有效
- [ ] 漏洞严重性多选过滤有效

### 13.4 Phase 4 验收（1.5 天）

- [ ] 基线 Tab 显示 SCA 检查结果（至少 1 个真实资产验证）
- [ ] 标签管理弹窗的 tag_key 下拉从字典来
- [ ] 修改字典后前端 label 实时更新
- [ ] 全部 E2E Playwright 用例通过

### 13.5 整体验收

- [ ] 49 → 70+ in-process 测试全绿
- [ ] 详情页 LCP < 2.5s（桌面）
- [ ] SOC 真实场景验证：进一台高危资产，30s 内能找到所有 CVE 和高危端口
- [ ] 文档：review 文档更新 v1.2 + 本设计文档 1.0 都已 commit
- [ ] 5 个 DDL 脚本（init_soc_assets.sql 等）已同步

---

## 14. 待定项

以下问题在实施过程中按需确认：

1. **告警 Tab 是否要展示 agent_id 列**（同 IP 多 agent 的情况）
2. **漏洞 Tab 列表超过 500 是否要服务端导出 CSV**
3. **基线 Tab 是否要按 policy 折叠展示**（一个 agent 可能适用多个 policy）
4. **同步任务的失败告警**（sync_tasks.status='failed' 时是否发通知）
5. **`data_classification` 字段是否要加前端强制校验**（v2 后端默认 internal，UI 层不强制）
6. **标签字典化后，是否要支持"自定义标签键"**（超出预设之外的 key）
7. **Wazuh API 凭证轮换时是否要热更新**（当前是启动时读 .env）

---

## 15. 附录

### 15.1 文件变更总览（最终）

**新增（11 个）**：
- 后端：`models/wazuh_package.py`, `models/wazuh_vulnerability.py`, `models/wazuh_sca.py`
- 后端：`schemas/wazuh.py`
- 后端：`services/wazuh_sync.py`, `services/asset_summary.py`
- 后端：`api/wazuh.py`
- 后端：1 个 Alembic 迁移
- 前端：`api/alert.ts`, `api/wazuh.ts`
- 前端：`views/asset/detail/components/MetricCard.vue`
- 前端：`composables/useRelativeTime.ts`, `constants/highRiskPorts.ts`

**修改（11 个）**：
- 后端：`models/asset.py`, `models/__init__.py`
- 后端：`schemas/asset.py`
- 后端：`services/wazuh_client.py`
- 后端：`api/assets.py`
- 后端：`core/config.py`, `main.py`
- 前端：`views/asset/detail/index.vue`（重写）
- 前端：`api/asset.ts`
- 前端：`types/api/api.d.ts`
- 5 个 DDL 脚本

**删除（0 个）**：现有功能全部保留并升级

### 15.2 数据流速查

| 场景 | 数据来源 | 缓存 | 刷新 |
|---|---|---|---|
| 摘要卡 | 聚合查询（DB + OpenSearch） | 无（每次实时聚合） | 进页拉一次 + 手动刷新按钮 |
| 告警 Tab | OpenSearch `wazuh-alerts-*` 索引 | 无 | 进页拉一次 |
| 端口 Tab | `soc_asset_ports` | 现有 | 现有 |
| 应用 Tab | `soc_wazuh_packages` | 1h（APScheduler 同步） | 1h 自动 + 手动同步按钮（v3） |
| 漏洞 Tab | `soc_wazuh_vulnerabilities` | 1h | 1h 自动 + 手动 |
| 基线 Tab | `soc_wazuh_sca_results` | 1h | 1h 自动 + 手动 |
| 标签 | `soc_asset_tags` | 现有 | 现有 |
| 基本信息 | `soc_assets` + `soc_dicts` | 现有 | 现有 |

### 15.3 关键决策追溯

| 决策 | 来自 | 时间 |
|---|---|---|
| DB 缓存 + 同步 | user 选择 | 2026-06-03 brainstorming Q1 |
| 复用 sync_tasks | user 选择 | 2026-06-03 brainstorming Q2 |
| Tab 顺序: 摘要→应用→漏洞→端口→基线→告警 | user 提出 | 2026-06-03 brainstorming Q3 |
| 标签下掉 Tab，放基本信息卡 chip | user 备注 | 2026-06-03 brainstorming Q4 |
| 事件 Tab 完全下掉 | user 选择 | 2026-06-03 brainstorming Q4 |
| 基线用 Wazuh SCA | user 选择 | 2026-06-03 brainstorming Q4 |
| 告警只进摘要 | user 选择 | 2026-06-03 brainstorming Q4 |

---

## 16. 版本历史

| 版本 | 日期 | 变更说明 | 作者 |
|---|---|---|---|
| v1.0 | 2026-06-03 | 初始版本。基于 review doc v1.1 + brainstorming 决策产出 | Claude |

---

**下一步行动**：
1. 等用户 review 本设计文档
2. 用户确认后，按 4 阶段分 4 个 commit 实施（每个 phase 独立 commit + 验证）
3. 实施过程中如有偏差，回来更新本设计文档
