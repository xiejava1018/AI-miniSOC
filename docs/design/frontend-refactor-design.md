# AI-miniSOC 前端重构设计文档

**文档类型:** 技术设计文档
**创建日期:** 2026-05-29
**版本:** v1.0
**作者:** Claude

---

## 1. 项目概述

### 1.1 背景

AI-miniSOC 当前前端基于 Vue 3 + Element Plus + Vite 自建架构，已实现资产管理、事件管理、告警查看、系统管理等核心页面。但随着功能迭代，以下问题逐渐显现：

- 页面风格不统一，部分页面从零搭建，缺乏设计规范
- 暗色主题未实现，SOC 监控场景长时间使用对视力不友好
- 权限控制仅到菜单级，缺少按钮/元素级权限
- 表格、表单等重复代码多，没有统一的 CRUD 生成器
- 路由和菜单配置分散在前端代码中，与后端菜单管理 API 未能联动

### 1.2 重构目标

1. **统一设计规范**：采用成熟 Admin 框架作为基础，确保所有页面风格一致
2. **实现暗色主题**：支持一键切换亮/暗模式，适配 SOC 监控场景
3. **增强权限控制**：从菜单级权限扩展到元素级权限（按钮可见性、操作权限）
4. **后端驱动菜单**：菜单配置完全由后端 API 驱动，前后端契约严格对齐
5. **提升开发效率**：复用框架内置的表格/表单生成器、状态管理、网络请求封装
6. **保持后端兼容**：后端 FastAPI API 完全不变，仅前端重构

### 1.3 非目标

- 不修改后端 API 接口（保持 100% 兼容）
- 不引入新的技术栈（继续使用 Vue 3 + Element Plus + TypeScript）
- 不增加国际化支持（保持中文单语）
- 不实现多租户（当前为单租户架构）

---

## 2. 技术选型

### 2.1 候选方案对比

| 维度 | art-design-pro (原版) | art-design-pro-edge (二开版) |
|------|----------------------|----------------------------|
| 技术栈 | Vue3 + Vite + TS + Element Plus + Tailwind | 完全一致 |
| 国际化 | 内置 i18n，中英切换 | **已移除**，纯中文 |
| 演示页面 | 30+ 演示/示例页面 | **已清理**，仅保留工作台 |
| 权限模型 | RBAC + 动态路由 + 菜单权限 | **+ 元素级权限** + 平台/系统分层 |
| 菜单驱动 | 前端配置为主 | **完全后端驱动**，严格契约 |
| 多租户 | 无 | **内置多租户** |
| 验证码登录 | 无 | 图形验证码 + 租户编码 |
| UI 规范 | 通用 Admin 风格 | **企业级优化**：表格居中、空值占位 `--`、操作列统一 |
| 网络异常 | 基础 | **内置异常处理** + 持久化存储校验 |
| 全局水印 | 无 | **默认开启** |
| 社区活跃度 | ~1.7k stars，活跃维护 | Fork 版，跟随上游同步 |

### 2.2 选型结论

**选用：art-design-pro-edge**

核心理由：

1. **后端契约对齐**：edge 强调"严格遵守后端契约，不为兼容上游而前端造字段"，与 AI-miniSOC FastAPI 后端设计理念一致
2. **权限系统匹配**：AI-miniSOC 后端已有 `用户 → 角色 → 菜单 → 元素权限` 四级体系，edge 恰好支持元素级权限
3. **中文单语更干净**：原版所有文案通过 `$t()` 国际化 key 管理，edge 已替换为纯中文静态字符串
4. **演示页面已清理**：原版 30+ 演示目录，edge 已删除，重构起点更干净
5. **网络异常处理**：SOC 系统对稳定性要求高，edge 内置了网络异常处理和本地数据持久化校验

需要剥离的成本：

- 多租户代码（约 1-2 天）：删除租户管理页面、`tenant_code` 字段、平台菜单等
- API 路径调整（约 0.5 天）：edge 接口前缀 `/api/v1/private/admin/system` → AI-miniSOC 的 `/api/v1`

---

## 3. 架构设计

### 3.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    AI-miniSOC Frontend                       │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐ │
│  │  Views      │  │  Components │  │  API Clients        │ │
│  │  (页面)      │  │  (组件)      │  │  (接口封装)          │ │
│  │             │  │             │  │                     │ │
│  │ Dashboard   │  │ ArtTable    │  │ Auth API            │ │
│  │ Assets      │  │ ArtForm     │  │ Asset API           │ │
│  │ Incidents   │  │ ArtSearchBar│  │ Incident API        │ │
│  │ Alerts      │  │ ArtStatsCard│  │ Alert API           │ │
│  │ System Mgmt │  │ ArtWatermark│  │ Sync API            │ │
│  │ ...         │  │ ...         │  │ ...                 │ │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘ │
│         │                │                    │            │
│  ┌──────┴────────────────┴────────────────────┴──────────┐ │
│  │                    Store (Pinia)                        │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐  │ │
│  │  │ Auth    │ │ User    │ │ Menu    │ │ Theme       │  │ │
│  │  │ Store   │ │ Store   │ │ Store   │ │ Store       │  │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────┘  │ │
│  └─────────────────────────────────────────────────────────┘ │
│         │                                                    │
│  ┌──────┴──────────────────────────────────────────────────┐│
│  │                  Core Framework                          ││
│  │  Vue3 + Vite + TypeScript + Element Plus + Tailwind     ││
│  │  Vue Router + Pinia + Axios + ECharts                   ││
│  └──────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │   AI-miniSOC      │
                    │   Backend (FastAPI)│
                    └───────────────────┘
```

### 3.2 目录结构（重构后）

```
src/frontend/
├── public/                          # 静态资源
│   └── icons.svg                    # 图标精灵
│
├── src/
│   ├── api/                         # API 客户端层
│   │   ├── auth.ts                  # 认证接口
│   │   ├── user.ts                  # 用户接口
│   │   ├── role.ts                  # 角色接口
│   │   ├── menu.ts                  # 菜单接口
│   │   ├── asset.ts                 # 资产接口
│   │   ├── asset-port.ts            # 资产端口接口
│   │   ├── incident.ts              # 事件接口
│   │   ├── alert.ts                 # 告警接口
│   │   ├── sync.ts                  # 同步接口
│   │   ├── audit-log.ts             # 审计日志接口
│   │   ├── ai.ts                    # AI分析接口
│   │   └── client.ts                # Axios 统一封装
│   │
│   ├── components/                  # 公共组件
│   │   ├── core/                    # 框架核心组件
│   │   │   ├── cards/               # 统计卡片
│   │   │   ├── tables/              # 高级表格
│   │   │   ├── forms/               # 表单生成器
│   │   │   ├── search/              # 搜索条
│   │   │   └── others/              # 水印、面包屑等
│   │   └── business/                # 业务组件（复用）
│   │       ├── AssetCard.vue        # 资产信息卡片
│   │       ├── AlertBadge.vue       # 告警级别标签
│   │       ├── SeverityTag.vue      # 严重级别标签
│   │       └── StatusTag.vue        # 状态标签
│   │
│   ├── views/                       # 页面视图
│   │   ├── auth/                    # 认证相关
│   │   │   └── login/
│   │   │       └── index.vue        # 登录页
│   │   │
│   │   ├── dashboard/               # 仪表盘
│   │   │   └── console/
│   │   │       └── index.vue        # 工作台（首页）
│   │   │
│   │   ├── assets/                  # 资产管理
│   │   │   ├── index.vue            # 资产列表
│   │   │   └── detail/
│   │   │       └── index.vue        # 资产详情
│   │   │
│   │   ├── incidents/               # 事件管理
│   │   │   ├── index.vue            # 事件列表
│   │   │   └── detail/
│   │   │       └── index.vue        # 事件详情
│   │   │
│   │   ├── alerts/                  # 告警查看
│   │   │   └── index.vue            # 告警列表 + AI分析
│   │   │
│   │   ├── sync/                    # 同步管理
│   │   │   ├── history/
│   │   │   │   └── index.vue        # 同步历史
│   │   │   └── detail/
│   │   │       └── index.vue        # 同步详情
│   │   │
│   │   └── system/                  # 系统管理
│   │       ├── user/
│   │       │   └── index.vue        # 用户管理
│   │       ├── role/
│   │       │   └── index.vue        # 角色管理
│   │       ├── menu/
│   │       │   └── index.vue        # 菜单管理
│   │       └── audit-log/
│   │           └── index.vue        # 审计日志
│   │
│   ├── router/                      # 路由管理
│   │   ├── index.ts                 # 路由入口
│   │   └── guard.ts                 # 路由守卫（认证 + 权限）
│   │
│   ├── store/                       # Pinia 状态管理
│   │   ├── modules/
│   │   │   ├── user.ts              # 用户状态
│   │   │   ├── menu.ts              # 菜单状态（后端驱动）
│   │   │   ├── theme.ts             # 主题状态
│   │   │   └── permission.ts        # 权限状态
│   │   └── index.ts                 # Store 入口
│   │
│   ├── types/                       # TypeScript 类型定义
│   │   ├── api.d.ts                 # API 响应类型
│   │   ├── user.d.ts                # 用户相关类型
│   │   ├── asset.d.ts               # 资产相关类型
│   │   └── menu.d.ts                # 菜单相关类型
│   │
│   ├── utils/                       # 工具函数
│   │   ├── request.ts               # HTTP 请求封装
│   │   ├── auth.ts                  # 认证工具
│   │   ├── format.ts                # 数据格式化
│   │   └── permission.ts            # 权限校验工具
│   │
│   ├── hooks/                       # 组合式函数
│   │   ├── useTable.ts              # 表格通用逻辑
│   │   ├── useForm.ts               # 表单通用逻辑
│   │   ├── usePermission.ts         # 权限控制
│   │   └── useTheme.ts              # 主题切换
│   │
│   ├── config/                      # 全局配置
│   │   ├── app.ts                   # 应用配置
│   │   ├── theme.ts                 # 主题配置
│   │   └── headerBar.ts             # 顶栏配置
│   │
│   ├── styles/                      # 全局样式
│   │   ├── variables.scss           # SCSS 变量
│   │   ├── element-override.scss    # Element Plus 覆盖
│   │   └── dark.scss                # 暗色主题覆盖
│   │
│   ├── App.vue                      # 根组件
│   ├── main.ts                      # 入口文件
│   └── theme.css                    # 主题 CSS 变量
│
├── .env                             # 环境变量（本地）
├── .env.example                     # 环境变量模板
├── vite.config.ts                   # Vite 配置
├── tsconfig.json                    # TypeScript 配置
├── tailwind.config.js               # Tailwind 配置
└── package.json                     # 依赖管理
```

---

## 4. 关键设计决策

### 4.1 菜单与路由：完全后端驱动

**现状问题**：当前前端路由在前端代码中硬编码，后端菜单 API 仅用于显示，两者未联动。

**重构方案**：

```typescript
// 后端返回的菜单结构（保持不变）
interface MenuItem {
  id: number
  name: string           // 显示名称
  path: string           // 路由路径
  component: string      // 组件路径
  icon?: string
  parent_id?: number
  sort_order: number
  is_hidden: boolean
  meta: {
    title: string
    icon?: string
    keepAlive?: boolean
    isHide?: boolean
  }
}

// 前端动态注册路由
async function generateRoutes(menus: MenuItem[]) {
  const routes = menus.map(menu => ({
    path: menu.path,
    name: menu.name,
    component: () => import(`@/views/${menu.component}`),
    meta: menu.meta,
    children: menu.children?.map(generateRoute)
  }))
  router.addRoute(routes)
}
```

**约束**：
- 菜单 `meta` 仅使用约定字段（`title`、`icon`、`keepAlive`、`isHide`）
- 禁止引入前端私有字段（如 `showBadge`、`fixedTab`、`roles`）
- 前端不做字段重映射，直接使用后端返回的字段名

### 4.2 权限控制：四级权限体系

```
用户 ──→ 角色 ──→ 菜单 ──→ 元素权限（按钮/操作）
```

**实现方式**：

```vue
<!-- 按钮级权限控制 -->
<template>
  <!-- 使用鉴权指令 -->
  <el-button v-permission="'asset:create'" type="primary">创建资产</el-button>
  
  <!-- 或使用权限 hook -->
  <el-button v-if="hasPermission('asset:delete')" type="danger">删除</el-button>
  
  <!-- 操作列：不超过3个直出，超过收起下拉菜单 -->
  <el-table-column label="操作">
    <template #default="{ row }">
      <el-button v-permission="'asset:edit'" link @click="edit(row)">编辑</el-button>
      <el-button v-permission="'asset:delete'" link type="danger" @click="del(row)">删除</el-button>
    </template>
  </el-table-column>
</template>
```

### 4.3 暗色主题实现

```scss
// styles/variables.scss
:root {
  --bg-primary: #ffffff;
  --bg-secondary: #f5f7fa;
  --text-primary: #303133;
  --text-secondary: #606266;
  --border-color: #e4e7ed;
  --primary-color: #409eff;
}

[data-theme="dark"] {
  --bg-primary: #1e1e1e;
  --bg-secondary: #252526;
  --text-primary: #d4d4d4;
  --text-secondary: #9cdcfe;
  --border-color: #3e3e42;
  --primary-color: #4ec9b0;
}
```

**SOC 场景优化**：
- 降低整体对比度，减少长时间监控的视力疲劳
- 告警级别颜色在暗色下保持辨识度（Critical=亮红，High=橙，Medium=黄，Low=蓝）
- 图表使用暗色 palette

### 4.4 HTTP 请求封装

**约定规则**：
- GET 查询参数自动清理空值（保留 `0`/`false`）
- 仅做必要的最小 UI 映射
- 认证字段保持：`access_token`、`refresh_token`
- 统一错误处理：401 → 跳转登录，403 → 提示无权限，500 → 显示服务端错误信息

```typescript
// api/client.ts 核心逻辑
const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 30000
})

// 请求拦截器：自动添加 Token
client.interceptors.request.use(config => {
  const token = useUserStore().accessToken
  if (token) config.headers.Authorization = `Bearer ${token}`
  
  // GET 请求清理空值
  if (config.method === 'get' && config.params) {
    config.params = Object.fromEntries(
      Object.entries(config.params).filter(([_, v]) => 
        v !== undefined && v !== null && v !== '' && !(typeof v === 'string' && v.trim() === '')
      )
    )
  }
  return config
})

// 响应拦截器：统一错误处理
client.interceptors.response.use(
  response => response.data,
  error => {
    const { response } = error
    if (response?.status === 401) {
      useUserStore().logout()
      router.push('/login')
    }
    return Promise.reject(response?.data?.detail || '请求失败')
  }
)
```

### 4.5 现有页面迁移映射

| 现有页面 | 重构后位置 | 迁移方式 | 工作量 |
|---------|-----------|---------|--------|
| `views/Assets.vue` | `views/assets/index.vue` | 迁移 + 使用 ArtTable | 中 |
| `views/AssetDetail.vue` | `views/assets/detail/index.vue` | 迁移 + 新布局 | 中 |
| `views/Incidents.vue` | `views/incidents/index.vue` | 迁移 + 使用 ArtTable | 中 |
| `views/IncidentDetail.vue` | `views/incidents/detail/index.vue` | 迁移 | 低 |
| `views/Alerts.vue` | `views/alerts/index.vue` | 迁移 + AI分析面板 | 中 |
| `views/SyncHistory.vue` | `views/sync/history/index.vue` | 迁移 + 新布局 | 低 |
| `views/SyncTaskDetail.vue` | `views/sync/detail/index.vue` | 迁移 | 低 |
| `views/system/Users.vue` | `views/system/user/index.vue` | 迁移 + 使用 ArtTable/ArtForm | 中 |
| `views/system/Roles.vue` | `views/system/role/index.vue` | 迁移 + 菜单权限分配 | 中 |
| `views/system/Menus.vue` | `views/system/menu/index.vue` | 迁移 + 树形组件 | 中 |
| `views/system/AuditLogs.vue` | `views/system/audit-log/index.vue` | 迁移 + 使用 ArtTable | 低 |
| `views/Dashboard.vue` | `views/dashboard/console/index.vue` | 重新设计 KPI + 图表 | 高 |
| `views/Login.vue` | `views/auth/login/index.vue` | 使用框架登录页 + 适配 | 低 |

---

## 5. 实施计划

### 5.1 阶段划分

| 阶段 | 内容 | 预估时间 | 产出 |
|------|------|---------|------|
| **Phase 1** | 框架搭建与剥离 | 3-5 天 | 可运行的基础框架 |
| **Phase 2** | 核心页面迁移 | 5-7 天 | 资产/事件/告警/系统管理 |
| **Phase 3** | 仪表盘与优化 | 3-4 天 | 工作台 + 暗色主题 |
| **Phase 4** | 测试与调优 | 2-3 天 | E2E 测试 + 性能优化 |
| **总计** | | **13-19 天** | |

### 5.2 Phase 1 详细任务

**Task 1: Fork art-design-pro-edge 并初始化**
- Fork 仓库到 AI-miniSOC 组织
- 调整 package.json（项目名称、版本）
- 配置 `.env`（API 地址、标题等）

**Task 2: 剥离多租户代码**
- 删除租户管理页面（`views/system/tenant`）
- 删除 `tenant_code` 字段和租户相关逻辑
- 删除平台菜单页面（`views/platform`）
- 简化登录流程（移除租户选择）

**Task 3: 调整 API 契约**
- 修改 `src/api/auth.ts`：调整登录/获取用户信息接口路径
- 修改 `src/api/client.ts`：基础 URL 从 `/api/v1/private/admin/system` → `/api/v1`
- 统一接口响应格式适配

**Task 4: 对接后端菜单 API**
- 修改 `src/api/menu.ts` 对接 AI-miniSOC 后端菜单接口
- 修改 `src/store/modules/menu.ts` 处理后端返回的菜单结构
- 测试动态路由注册

**Task 5: 对接后端权限 API**
- 修改 `src/api/role.ts` 对接角色/权限接口
- 实现 `v-permission` 指令
- 测试元素级权限控制

### 5.3 Phase 2 详细任务

**Task 6-8: 资产/事件/告警页面迁移**
- 逐个迁移现有页面到新的目录结构
- 使用 `ArtTable` 替换现有表格
- 使用 `ArtForm` 替换表单
- 保持现有业务逻辑不变

**Task 9-11: 系统管理页面迁移**
- 用户管理：使用框架用户管理模板
- 角色管理：对接后端角色 API，集成菜单权限分配
- 菜单管理：使用树形组件

### 5.4 Phase 3 详细任务

**Task 12: 工作台（Dashboard）重新设计**
- KPI 指标卡片（活跃告警、待处理事件、资产数、在线率）
- 告警趋势图（7天/30天）
- 严重性分布图（饼图/环形图）
- 最近活动时间线

**Task 13: 暗色主题适配**
- 配置 Element Plus 暗色变量
- 自定义暗色 palette（降低对比度）
- 图表暗色适配

### 5.5 Phase 4 详细任务

**Task 14: E2E 测试**
- 登录/登出流程
- 资产 CRUD
- 菜单权限验证

**Task 15: 性能优化**
- 路由懒加载
- 组件按需引入
- 图片/图标优化

---

## 6. 风险评估

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|---------|
| 多租户剥离不彻底 | 中 | 高 | 建立剥离检查清单，逐个文件审查 |
| API 路径遗漏 | 高 | 中 | 全局搜索所有 API 调用，统一替换 |
| 后端响应格式差异 | 高 | 中 | 提前对比所有接口的响应格式，建立映射表 |
| 暗色主题下告警颜色不醒目 | 中 | 中 | SOC 场景专项配色测试 |
| 动态路由注册失败 | 高 | 低 | 完善错误处理和 fallback 路由 |
| 迁移期间功能回退 | 中 | 低 | 保持旧前端可运行，新前端并行开发 |

---

## 7. 相关资源

- **art-design-pro**: https://github.com/Daymychen/art-design-pro
- **art-design-pro-edge**: https://github.com/ChnMig/art-design-pro-edge
- **Element Plus 暗色主题**: https://element-plus.org/zh-CN/guide/dark-mode.html
- **AI-miniSOC 后端 API 文档**: http://localhost:8000/docs

---

**文档维护**: 本文档应随重构进度同步更新，重大变更需记录变更历史。

| 版本 | 日期 | 变更说明 | 作者 |
|------|------|----------|------|
| v1.0 | 2026-05-29 | 初始版本 | Claude |
