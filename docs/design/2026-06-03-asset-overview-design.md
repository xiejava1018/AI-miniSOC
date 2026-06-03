# 资产概览页设计文档

**文档版本**: v1.0
**创建日期**: 2026-06-03
**最后更新**: 2026-06-03
**作者**: Claude
**基础**: 用户与 Claude brainstorming(2026-06-03)
**目标文件**:
- `src/frontend/src/views/asset/overview/index.vue` (新增)
- `src/frontend/src/views/dashboard/console/modules/asset-health.vue` (新增)
- `src/frontend/src/router/routesAlias.ts` (修改)
- `src/backend/app/api/assets.py` (修改)
- `src/backend/app/services/asset_overview.py` (新增)

---

## 目录

- [1. 概述](#1-概述)
- [2. 设计目标 & 非目标](#2-设计目标--非目标)
- [3. 已确认的设计决策](#3-已确认的设计决策)
- [4. 整体架构](#4-整体架构)
- [5. API 设计](#5-api-设计)
- [6. 前端设计](#6-前端设计)
- [7. 实施阶段](#7-实施阶段)
- [8. 测试策略](#8-测试策略)
- [9. 风险与缓解](#9-风险与缓解)
- [10. 验收标准](#10-验收标准)
- [11. 待定项](#11-待定项)
- [12. 版本历史](#12-版本历史)

---

## 1. 概述

### 1.1 背景

当前资产管理模块只有列表页(`/asset/list`)和详情页(`/asset/detail`)。SOC 拿不到全局资产视图,需要切到列表页手数或调 SQL,效率低。

Dashboard console 工作台(art-design-pro-edge 模板自带 6 个模块)全是占位数据,无 SOC 维度信息。

### 1.2 文档定位

- 补充 `ai-asset-management-prd.md` 中提及但未落地的"仪表盘:风险分布饼图 + Top10 高危资产"
- 配套 v2 资产详情页升级(`docs/design/2026-06-03-asset-detail-v2-design.md`),从"单资产视角"扩展到"全局资产视角"

### 1.3 核心设计哲学

**"1 秒钟看到全局,30 秒钟定位风险源"**

- 首屏 4 个 KPI(总资产/高危/告警/事件)直接回答"有多少事"
- 2 张分布图回答"资产结构长什么样"
- 1 张趋势图回答"最近怎么样"
- 2 张 Top 表回答"哪些资产最危险"

---

## 2. 设计目标 & 非目标

### 2.1 目标

1. ✅ **首屏即全局**:进概览页 1s 内 SOC 能回答"公司有多少资产?多少高危?"
2. ✅ **风险可定位**:Top 表直接给出"最该先看哪几台"
3. ✅ **详情可下钻**:图表/Top 表点 → 资产详情页
4. ✅ **秒开**:单聚合接口,1 次请求,目标 < 2s
5. ✅ **失败降级**:OpenSearch 挂不影响页面打开,告警相关字段显示 0
6. ✅ **不破坏现有**:console 工作台 6 个原模块保留,只追加"资产健康度"入口

### 2.2 非目标(v1 范围外)

- ❌ 漏洞分布 + Top CVE(等 Phase 2 Wazuh 漏洞缓存)
- ❌ SCA 合规率概览(等 Phase 4)
- ❌ 自动刷新(手动 reload 或重新进页)
- ❌ 时间范围切换(只展示 24h,不做 7d/30d 选项)
- ❌ 移动端适配(桌面优先)
- ❌ 实时 WebSocket 推送

---

## 3. 已确认的设计决策

| # | 决策点 | 选择 | 理由 |
|---|---|---|---|
| D1 | 页面位置 | 独立页 `/asset/overview` + console 入口卡 | 概览要画图布局自由;同时保留 console 入口方便 |
| D2 | 内容侧重 | SOC 风险全貌 | 服务 SOC 应急响应决策 |
| D3 | 数据范围 | 首版只上能用的(等 Phase 2 再加漏洞/SCA) | 2-3 天出活,不卡 Wazuh 接入 |
| D4 | 接口策略 | 1 次聚合 `GET /api/v1/assets/overview` | 避免 N+1,1 个请求搞定 |
| D5 | 趋势图粒度 | 24h × 1h 桶 | 24 个点足够呈现趋势,不会抖动 |
| D6 | 高危资产定义 | 5 条件命中任一(criticality=core + 任一告警/端口/事件;open_incidents>0;alert_24h≥10) | 显式公式,无歧义 |
| D7 | Top 10 评分 | criticality=core→100 + incidents×30 + ports×20 + (open_ports≥5→10) + alerts×1 | 覆盖多维度,critical 资产权重大 |
| D8 | 权限 | 沿用现有资产管理权限 | 不另开新权限,RBAC 最小变更 |
| D9 | 菜单位置 | 资产管理下挂"资产概览"作为第一个子项 | 高频入口前置 |
| D10 | 失败兜底 | 整页降级 + 局部降级双层 | OpenSearch 挂不影响资产数/分布图 |

---

## 4. 整体架构

### 4.1 页面结构

```
console 工作台 (/dashboard/console)
└── 新增「资产健康度」入口卡 (assets-health.vue)
    └── 数据源: GET /api/v1/assets/overview → kpi 字段
    └── 按钮「查看详情 →」→ router.push('/asset/overview')

资产概览 (/asset/overview, 新)
└── 1 个 page (~600 行)
    ├── 顶部 4 张 MetricCard(总资产/高危/告警/事件)
    ├── 中部 2 张环图(类型分布 + 在线状态)
    ├── 中部 1 张折线(24h 告警趋势,双轴:总+高危)
    └── 底部 2 张 Top 表(高危资产 + 告警资产)
```

### 4.2 数据流

```
Frontend (1 个 page)
    │
    │ GET /api/v1/assets/overview
    ▼
FastAPI (assets.py 新增 /overview 端点)
    │
    │ 委托给 AssetOverviewService
    ▼
AssetOverviewService (新)
    ├─ DB count → total_assets, open_incidents
    ├─ DB GROUP BY → by_type, by_status, by_criticality
    ├─ AlertQueryService → kpi.alerts_24h(无 IP,全公司)
    ├─ OpenSearch date_histogram(1h × 24) → alert_trend_24h
    ├─ 业务规则聚合 → top_risky_assets (Top 10)
    └─ OpenSearch top agents → top_alert_assets (Top 10)
```

### 4.3 菜单/路由变化

| 项 | 当前 | v1 后 |
|---|---|---|
| 路由别名 | `RoutesAlias.Assets = '/asset/list/index'` | 新增 `AssetOverview = '/asset/overview'` |
| 资产管理子菜单 | 资产列表 | **资产概览(新,1st)** → 资产列表 |
| Dashboard console | 6 个原模块 | 6 个原模块 + 资产健康度(末尾追加) |

---

## 5. API 设计

### 5.1 新增:`GET /api/v1/assets/overview`

**请求**:`GET /api/v1/assets/overview`(无参数,无 body,无分页)

**响应**(HTTP 200,body.code=200):
```json
{
  "code": 200,
  "msg": "success",
  "data": {
    "kpi": {
      "total_assets": 87,
      "high_risk_assets": 12,
      "alerts_24h": 145,
      "open_incidents": 5
    },
    "distribution": {
      "by_type": [
        {"key": "server", "count": 50},
        {"key": "workstation", "count": 30}
      ],
      "by_status": [
        {"key": "online", "count": 70},
        {"key": "offline", "count": 12},
        {"key": "unknown", "count": 5}
      ],
      "by_criticality": [
        {"key": "core", "count": 15},
        {"key": "important", "count": 40},
        {"key": "normal", "count": 32}
      ]
    },
    "alert_trend_24h": [
      {"hour": "2026-06-02T11:00:00Z", "total": 5, "critical": 1}
    ],
    "top_risky_assets": [
      {
        "id": "uuid",
        "ip": "192.168.0.35",
        "name": "pve-host2-35",
        "asset_type": "server",
        "criticality": "core",
        "score": 145,
        "factors": ["core 资产", "高危端口 1", "24h 告警 26"]
      }
    ],
    "top_alert_assets": [
      {
        "id": "uuid",
        "ip": "192.168.0.2",
        "name": "router",
        "asset_type": "router",
        "alert_24h": 312,
        "alert_critical_24h": 4,
        "last_alert_at": "2026-06-03T10:00:00Z"
      }
    ]
  }
}
```

**实现要点**:
- `AssetOverviewService.build_overview()` 内部 6 步聚合,任何一步失败不影响其他
- `high_risk_assets` 用业务规则公式(见 D6)
- `top_risky_assets` 用评分公式(见 D7)按 score desc 排序,取前 10
- 趋势图时间范围固定 24h,`end_time=now`,`start_time=end_time - 24h`
- Top 告警资产用 OpenSearch top by `agent.ip` 聚合,补 0 的告警资产不进 Top

**性能预算**:
- 目标 P95 < 2s(本地)
- OpenSearch date_histogram 单查询最慢,需 < 1.5s
- DB 查询 6 个全部 < 100ms

### 5.2 错误兜底矩阵

| 失败点 | 兜底行为 |
|---|---|
| OpenSearch 完全挂(告警聚合失败) | `kpi.alerts_24h=0`,trend 全 0,Top 告警表空;logger.warning 不抛错 |
| OpenSearch 超时(>3s) | 同上 + 后端 warn |
| DB count 失败 | 该 kpi 字段 0,图表 EmptyState 提示"暂无数据" |
| 单资产 score 计算异常 | 该资产从 Top 剔除,日志 warn |
| 主接口 5xx | 整页降级:4 个 KPI 显示 —,所有图表 EmptyState,顶部 ElAlert 提示"数据加载失败,稍后重试" |
| dict 缺 label | 走 `dictStore.getLabelMap()` 兜底回 key 原值 |

---

## 6. 前端设计

### 6.1 组件树

```
views/asset/overview/index.vue (~600 行)
├── ElCard (KPI 区,无 header)
│   └── <MetricCard> × 4  (复用 v2 详情页组件)
│       ├── 总资产 (info)
│       ├── 高危资产 (danger, 当 >0 时)
│       ├── 24h 告警 (danger, 当 >0 时)
│       └── 未关闭事件 (warning, 当 >0 时)
│
├── ElCard (资产分布)
│   ├── ElRow: 2 列
│   │   ├── 类型分布环图 (ECharts)
│   │   └── 在线状态分布环图 (ECharts)
│   └── 24h 告警趋势折线图 (ECharts,双轴)
│
├── ElCard (Top 10 高危资产)
│   └── ElTable: IP | 名称 | 类型 | 评分 | 风险因子 | 操作
│       └── 行可点 → /asset/detail/{id}
│
└── ElCard (Top 10 告警资产)
    └── ElTable: IP | 名称 | 类型 | 24h 告警 | 高危告警 | 最近告警时间
        └── 行可点 → /asset/detail/{id}

views/dashboard/console/modules/asset-health.vue (~150 行)
├── ElCard 标题"资产健康度" + 右上角"查看详情 →"按钮
├── 内部 4 个 MetricCard 横排
└── 数据从 overview 接口 kpi 字段取
```

### 6.2 新增/修改的文件

| 文件 | 动作 | 说明 |
|---|---|---|
| `src/backend/app/services/asset_overview.py` | **新增** | 概览聚合服务 |
| `src/backend/app/api/assets.py` | **修改** | 加 `GET /overview` 端点 |
| `src/backend/tests/test_asset_overview.py` | **新增** | 概览服务 + 端点测试 |
| `src/frontend/src/api/asset.ts` | **修改** | 加 `getAssetOverview()` |
| `src/frontend/src/types/api/api.d.ts` | **修改** | 加 `Api.Asset.AssetOverview` 类型 |
| `src/frontend/src/views/asset/overview/index.vue` | **新增** | 概览主页面 |
| `src/frontend/src/views/dashboard/console/modules/asset-health.vue` | **新增** | console 入口卡 |
| `src/frontend/src/views/dashboard/console/index.vue` | **修改** | 末尾追加 AssetHealth 模块 |
| `src/frontend/src/router/routesAlias.ts` | **修改** | 加 `AssetOverview` 别名 |
| 后端菜单 SQL/seed | **修改** | 资产管理下加"资产概览"菜单项 |

### 6.3 关键 UI 模式

**双轴折线图**(ECharts):
```ts
option = {
  tooltip: { trigger: 'axis' },
  legend: { data: ['总告警', '高危告警'] },
  xAxis: { type: 'category', data: hours },
  yAxis: [
    { type: 'value', name: '总告警' },
    { type: 'value', name: '高危', position: 'right' }
  ],
  series: [
    { name: '总告警', type: 'line', data: totals, smooth: true },
    { name: '高危告警', type: 'line', yAxisIndex: 1, data: criticals, lineStyle: { type: 'dashed' } }
  ]
}
```

**风险因子 ElTag 串**:
```vue
<ElTag v-for="f in row.factors" :key="f" type="danger" effect="plain" size="small">
  {{ f }}
</ElTag>
```

**Top 表行可点**:
```vue
<ElTable :data="topRisky" @row-click="(row) => $router.push(`/asset/detail/${row.id}`)">
```

---

## 7. 实施阶段

### 7.1 阶段一(2-3 天):后端 + 概览页骨架

1. 后端:`AssetOverviewService` + `GET /api/v1/assets/overview` 端点
2. 后端测试:`test_asset_overview.py`(happy path + 各种失败兜底)
3. 前端:类型 + API 封装
4. 前端:概览页骨架(4 KPI + 2 环图 + 1 折线 + 2 Top 表,空数据 OK)
5. 前端:console 入口卡

### 7.2 阶段二(0.5 天):菜单/路由/权限

1. `RoutesAlias.AssetOverview` + 路由配置
2. 侧边栏菜单"资产概览"子项
3. 权限沿用资产管理,数据库 seed 加菜单项

### 7.3 阶段三(0.5 天):收尾

1. 整页降级态样式调优
2. 移动端最简适配(可选)
3. 跑全部测试确认无回归
4. commit

---

## 8. 测试策略

### 8.1 后端

| 类型 | 覆盖 | 工具 |
|---|---|---|
| 单元 | `AssetOverviewService.build_overview()` 6 步聚合 | pytest + unittest.mock |
| 单元 | 评分公式边界(0 分/100 分/1000 分) | pytest parametrize |
| 单元 | 高危资产定义 5 条件命中分支 | pytest parametrize |
| 集成 | `GET /overview` 端点 200 + envelope | pytest + TestClient |
| 失败兜底 | OpenSearch 异常、DB 异常、超时 | pytest + mock |

**目标覆盖率**:> 80%

### 8.2 前端

| 类型 | 覆盖 |
|---|---|
| 组件 | `AssetHealth` 渲染 + 跳转 |
| E2E | 进概览页 → 看到 4 KPI → 点 Top 资产 → 进详情页 |

### 8.3 手动验收(必做)

- 真实环境加载时间 < 2s
- 故意把 OpenSearch 停掉,页面降级,4 KPI 不挂
- 故意让 DB 没数据,kpi=0,图表显示"暂无数据"不报错

---

## 9. 风险与缓解

| # | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R1 | OpenSearch 慢导致概览页 > 3s | 中 | 内部 3s 超时,超时降级;后续可加缓存(Redis 30s) |
| R2 | top_risky_assets 计算耗时长(扫描所有资产) | 低 | 当前资产数 87,SQL 单查询 < 100ms;100+ 再考虑优化 |
| R3 | 趋势图 0 点边界(刚好 0:00) | 低 | `start_time=end_time-24h` 自然覆盖,测试覆盖 |
| R4 | dict 缺 label | 低 | `dictStore.getLabelMap()` 走兜底,key 原值 |
| R5 | 概览页加菜单后,RBAC 报错没权限 | 低 | 沿用现有资产管理权限,SQL seed 直接挂父菜单下 |
| R6 | ECharts 体积影响打包 | 低 | 项目已用 ECharts,无新依赖 |
| R7 | 趋势图 X 轴 24 点在不同 viewport 下挤 | 低 | X 轴 `axisLabel.interval: 'auto'` 或固定 1,2,4,8,12 |

---

## 10. 验收标准

- [ ] 概览页加载 < 2s(P95,本地)
- [ ] 4 张 KPI 卡显示真实数字(总资产/高危/告警/事件)
- [ ] 类型分布环图鼠标悬停显示百分比
- [ ] 24h 告警趋势折线图双轴清晰
- [ ] Top 10 高危资产表可点行进详情
- [ ] Top 10 告警资产表显示"24h 告警""高危告警""最近告警时间"
- [ ] Console 工作台末尾出现"资产健康度"卡,数字与概览页一致
- [ ] 侧边栏"资产管理"下"资产概览"作为第一个子项
- [ ] OpenSearch 停掉后页面不挂,告警相关字段 0/空
- [ ] 全部后端测试通过(> 80% 覆盖)
- [ ] vue-tsc 无新增错误

---

## 11. 待定项

1. 趋势图是否要做"时间范围切换"(24h/7d/30d)
2. 概览页是否要加"导出 PDF 报告"按钮
3. Top 10 高危资产的"风险因子"是否要可点击跳到资产详情页对应 Tab
4. 是否要做"高危资产变化趋势"对比昨日
5. console 入口卡是否要做"鼠标悬停迷你预览"

---

## 12. 版本历史

| 版本 | 日期 | 变更说明 | 作者 |
|---|---|---|---|
| v1.0 | 2026-06-03 | 初始版本。基于 2026-06-03 用户与 Claude brainstorming 决策产出 | Claude |
