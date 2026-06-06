# AI-miniSOC Code Wiki

## 目录
- [项目概述](#项目概述)
- [技术架构](#技术架构)
- [后端架构](#后端架构)
- [前端架构](#前端架构)
- [数据库模型](#数据库模型)
- [API接口文档](#api接口文档)
- [依赖关系](#依赖关系)
- [项目运行方式](#项目运行方式)
- [开发规范](#开发规范)

---

## 项目概述

### 项目简介
**AI-miniSOC** 是一个 AI 驱动的微型安全运营中心（Security Operations Center）平台，集成了多种安全工具，提供智能化的安全监控、威胁检测和事件响应能力。

### 核心功能
1. **日志聚合与分析** - 基于 Loki 和 Grafana 的日志系统
2. **威胁检测** - 集成 Wazuh SIEM 的威胁检测
3. **主机监控** - 系统健康检查和性能监控
4. **资产管理** - 资产台账、Wazuh 同步、端口管理、标签分类
5. **AI 能力** - 智能分析、异常检测、趋势预测

### 项目结构
```
AI-miniSOC/
├── configs/              # 配置文件
├── docs/                 # 项目文档
│   ├── api/              # API 文档
│   ├── design/           # 设计文档
│   └── installation/     # 安装指南
├── scripts/              # 工具脚本
├── services/             # 微服务
│   └── wazuh-api-proxy/  # Wazuh API 代理
├── src/                  # 源代码
│   ├── backend/          # 后端服务
│   └── frontend/         # 前端应用
├── skills/               # Claude 技能
├── .claude-plugin/       # Claude 插件
└── README.md
```

---

## 技术架构

### 技术栈
| 层级 | 技术选型 |
|------|---------|
| **后端框架** | FastAPI 0.115.0 |
| **前端框架** | Vue 3 + TypeScript + Element Plus |
| **数据库** | PostgreSQL |
| **ORM** | SQLAlchemy 2.0.36 |
| **认证** | JWT (python-jose) |
| **日志系统** | Loki + Grafana |
| **SIEM** | Wazuh |
| **搜索引擎** | OpenSearch |
| **状态管理** | Pinia |
| **路由** | Vue Router 4 |
| **图表** | ECharts |

### 系统架构图
```
┌─────────────────────────────────────────────────────────┐
│                        前端层                             │
│                    (Vue 3 + Element Plus)                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ 资产模块  │  │ 告警模块  │  │ 系统管理  │  │ 仪表盘  │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
└─────────────────────────────────────────────────────────┘
                            ↓ REST API
┌─────────────────────────────────────────────────────────┐
│                       后端层                              │
│                     (FastAPI)                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ 认证模块  │  │ 资产模块  │  │ AI分析模块 │  │ 同步服务  │ │
│  └──────────┘  └──────────┘  └──────────┘  └─────────┘ │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                      数据存储层                           │
│  ┌────────────┐  ┌──────────┐  ┌──────────┐             │
│  │ PostgreSQL │  │   Loki   │  │ OpenSearch│             │
│  └────────────┘  └──────────┘  └──────────┘             │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                      数据采集层                           │
│  ┌────────────┐  ┌──────────┐  ┌──────────┐             │
│  │   Wazuh    │  │ Filebeat │  │ 自定义采集 │             │
│  └────────────┘  └──────────┘  └──────────┘             │
└─────────────────────────────────────────────────────────┘
```

---

## 后端架构

### 后端项目结构
```
src/backend/
├── app/
│   ├── api/              # API 路由
│   │   ├── __init__.py
│   │   ├── ai.py
│   │   ├── alerts.py
│   │   ├── assets.py
│   │   ├── audit_logs.py
│   │   ├── auth.py
│   │   ├── departments.py
│   │   ├── deps.py
│   │   ├── dicts.py
│   │   ├── incidents.py
│   │   ├── menus.py
│   │   ├── roles.py
│   │   ├── sync.py
│   │   └── users.py
│   ├── core/             # 核心模块
│   │   ├── __init__.py
│   │   ├── audit_decorator.py
│   │   ├── auth.py
│   │   ├── captcha.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── permissions.py
│   │   ├── response_wrapper.py
│   │   ├── security.py
│   │   └── token_blacklist.py
│   ├── models/           # 数据库模型
│   ├── schemas/          # Pydantic 数据模式
│   └── services/         # 业务逻辑服务
├── alembic/              # 数据库迁移
├── tests/                # 测试用例
├── main.py               # 应用入口
├── requirements.txt      # Python 依赖
└── start.sh              # 启动脚本
```

### 核心模块说明

#### 1. API 层 (`app/api/`)
- **职责**: 定义 REST API 端点，处理 HTTP 请求和响应
- **主要模块**:
  - [auth.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/api/auth.py) - 认证相关接口（登录、登出、token 刷新）
  - [assets.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/api/assets.py) - 资产管理接口
  - [users.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/api/users.py) - 用户管理接口
  - [ai.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/api/ai.py) - AI 分析接口
  - [sync.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/api/sync.py) - 资产同步接口

#### 2. 核心层 (`app/core/`)
- **职责**: 提供基础设施支持
- **主要模块**:
  - [config.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/core/config.py) - 配置管理（环境变量、数据库连接等）
  - [database.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/core/database.py) - 数据库连接和会话管理
  - [auth.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/core/auth.py) - JWT 认证和 token 管理
  - [security.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/core/security.py) - 密码哈希和验证
  - [captcha.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/core/captcha.py) - 验证码生成和验证
  - [token_blacklist.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/core/token_blacklist.py) - Token 黑名单管理

#### 3. 模型层 (`app/models/`)
- **职责**: 定义数据库表结构和关系
- **主要模型**:
  - [user.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/models/user.py) - 用户模型
  - [asset.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/models/asset.py) - 资产模型
  - [asset_port.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/models/asset_port.py) - 资产端口模型
  - [sync_task.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/models/sync_task.py) - 同步任务模型
  - [audit_log.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/models/audit_log.py) - 审计日志模型

#### 4. 服务层 (`app/services/`)
- **职责**: 实现核心业务逻辑
- **主要服务**:
  - [asset_sync.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/services/asset_sync.py) - 资产同步服务（从 Wazuh 同步）
  - [asset_overview.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/services/asset_overview.py) - 资产概览服务
  - [asset_summary.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/services/asset_summary.py) - 资产安全摘要服务
  - [audit_log_service.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/services/audit_log_service.py) - 审计日志服务
  - [wazuh_client.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/services/wazuh_client.py) - Wazuh API 客户端

#### 5. 应用入口 ([main.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/main.py))
- 创建 FastAPI 应用实例
- 配置 CORS 中间件
- 注册 API 路由
- 提供健康检查和根路径

### 关键类和函数

#### `Settings` ([config.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/core/config.py))
配置管理类，负责从环境变量读取配置。

**主要配置项**:
- `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` - 数据库连接
- `TEST_DB_NAME` - 测试数据库名
- `GLM_API_KEY`, `GLM_MODEL`, `GLM_API_BASE` - 智谱 AI 配置
- `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES` - JWT 配置
- `WAZUH_API_URL`, `WAZUH_API_USERNAME`, `WAZUH_API_PASSWORD` - Wazuh 配置
- `BACKEND_CORS_ORIGINS` - CORS 允许的源

#### `Asset` 模型 ([asset.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/models/asset.py))
资产数据模型，表名 `soc_assets`。

**主要字段**:
- `id` - UUID 主键
- `network_segment` - 网络分段
- `network_zone` - 网络区域
- `asset_ip` - 资产 IP
- `name` - 资产名称
- `asset_type` - 资产类型
- `criticality` - 重要程度
- `asset_status` - 资产状态
- `data_source` - 数据来源（wazuh/manual）
- `wazuh_agent_id` - Wazuh Agent ID
- `owner` - 负责人
- `business_unit` - 业务单元
- `data_classification` - 数据分类
- `owner_contact` - 负责人联系电话
- `created_at`, `updated_at` - 时间戳

**关系**:
- `ports` - 一对多关系到 AssetPort
- `tags` - 一对多关系到 AssetTag

#### `AssetSyncService` ([asset_sync.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/services/asset_sync.py))
资产同步服务，负责从 Wazuh 同步资产。

**主要方法**:
- `sync_from_wazuh()` - 从 Wazuh 同步所有资产
- `sync_from_wazuh_with_tracking(sync_type)` - 带任务追踪的同步
- `_map_agent_to_asset(agent)` - 将 Wazuh Agent 映射为资产数据
- `_create_or_update_asset(asset_data)` - 创建或更新资产
- `_log_change(...)` - 记录变更日志

#### 认证 API ([auth.py](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/app/api/auth.py))
**主要接口**:
- `POST /auth/login` - 用户登录
- `GET /auth/captcha` - 获取验证码
- `POST /auth/refresh` - 刷新 token
- `POST /auth/logout` - 用户登出
- `GET /auth/me` - 获取当前用户信息

**安全特性**:
- 登录失败计数和账户锁定
- 验证码校验
- Token 轮换机制
- Token 黑名单
- 审计日志记录

---

## 前端架构

### 前端项目结构
```
src/frontend/
├── public/                # 静态资源
├── src/
│   ├── api/              # API 调用
│   │   ├── system/       # 系统管理 API
│   │   ├── asset.ts      # 资产管理 API
│   │   ├── auth.ts       # 认证 API
│   │   └── ...
│   ├── assets/           # 资源文件
│   │   ├── icons/        # 图标
│   │   ├── images/       # 图片
│   │   └── styles/       # 样式
│   ├── components/       # 组件
│   │   ├── business/     # 业务组件
│   │   └── core/         # 核心组件
│   ├── composables/      # 组合式函数
│   ├── constants/        # 常量
│   ├── directives/       # 指令
│   ├── enums/            # 枚举
│   ├── hooks/            # 钩子
│   ├── mock/             # Mock 数据
│   ├── plugins/          # 插件
│   ├── router/           # 路由
│   ├── store/            # 状态管理
│   ├── types/            # 类型定义
│   ├── utils/            # 工具函数
│   ├── views/            # 页面组件
│   │   ├── asset/        # 资产管理页面
│   │   │   ├── detail/   # 资产详情
│   │   │   ├── list/     # 资产列表
│   │   │   └── overview/ # 资产概览
│   │   ├── auth/         # 认证页面
│   │   ├── dashboard/    # 仪表盘
│   │   └── system/       # 系统管理
│   ├── App.vue           # 根组件
│   ├── main.ts           # 应用入口
│   └── env.d.ts          # 环境变量类型
├── package.json
├── pnpm-lock.yaml
└── ...
```

### 核心模块说明

#### 1. API 层 ([src/api/](file:///Users/xiejava/AIProject/AI-miniSOC/src/frontend/src/api/))
- **职责**: 封装后端 API 调用
- **主要模块**:
  - [asset.ts](file:///Users/xiejava/AIProject/AI-miniSOC/src/frontend/src/api/asset.ts) - 资产管理 API
    - `getAssetList()` - 获取资产列表
    - `getAssetDetail(id)` - 获取资产详情
    - `getAssetSummary(id)` - 获取资产安全摘要
    - `getAssetOverview()` - 获取资产概览
    - `syncFromWazuh()` - 从 Wazuh 同步资产
    - `getAssetPorts()`, `addAssetPort()` 等 - 端口管理
  - [auth.ts](file:///Users/xiejava/AIProject/AI-miniSOC/src/frontend/src/api/auth.ts) - 认证 API
  - [alert.ts](file:///Users/xiejava/AIProject/AI-miniSOC/src/frontend/src/api/alert.ts) - 告警 API

#### 2. 路由层 ([src/router/](file:///Users/xiejava/AIProject/AI-miniSOC/src/frontend/src/router/))
- **职责**: 管理前端路由和权限
- **主要特性**:
  - 动态路由（基于菜单权限）
  - 路由守卫（前置/后置）
  - 路由权限验证

#### 3. 状态管理 ([src/store/](file:///Users/xiejava/AIProject/AI-miniSOC/src/frontend/src/store/))
- **职责**: 全局状态管理（Pinia）
- **主要模块**:
  - `user.ts` - 用户状态
  - `menu.ts` - 菜单状态
  - `system.ts` - 系统状态
  - `dict.ts` - 字典数据
  - `table.ts` - 表格状态

#### 4. 页面组件 ([src/views/](file:///Users/xiejava/AIProject/AI-miniSOC/src/frontend/src/views/))
- **资产模块**:
  - [asset/list/index.vue](file:///Users/xiejava/AIProject/AI-miniSOC/src/frontend/src/views/asset/list/index.vue) - 资产列表页
  - [asset/detail/index.vue](file:///Users/xiejava/AIProject/AI-miniSOC/src/frontend/src/views/asset/detail/index.vue) - 资产详情页
  - [asset/overview/index.vue](file:///Users/xiejava/AIProject/AI-miniSOC/src/frontend/src/views/asset/overview/index.vue) - 资产概览页
- **系统管理**:
  - 用户管理
  - 角色管理
  - 菜单管理
  - 部门管理
  - 审计日志

#### 5. 应用入口 ([main.ts](file:///Users/xiejava/AIProject/AI-miniSOC/src/frontend/src/main.ts))
- 创建 Vue 应用实例
- 初始化 Store
- 初始化 Router
- 注册全局指令
- 设置错误处理
- 预拉取系统信息

---

## 数据库模型

### ER 图（主要实体关系）
```
┌─────────────┐       ┌─────────────┐
│   User      │       │   Role      │
│─────────────│       │─────────────│
│ id (PK)     │┌─────│ id (PK)     │
│ username    │      │ code        │
│ password_hash│      │ name        │
│ email       │      │ ...         │
│ status      │      └─────────────┘
│ role_id (FK)│────┐
│ ...         │    │
└─────────────┘    │
                   │
┌─────────────┐    │       ┌─────────────┐
│   Asset     │    │       │ AuditLog    │
│─────────────│    │       │─────────────│
│ id (PK)     │    │       │ id (PK)     │
│ asset_ip    │    │       │ user_id (FK)│──┐
│ name        │    │       │ action      │  │
│ asset_type  │    │       │ ...         │  │
│ ...         │    │       └─────────────┘  │
└─────────────┘    │                        │
    │              │                        │
    │ (1:N)        │                        │
    │              └────────────────────────┘
    │
┌─────────────┐
│ AssetPort   │
│─────────────│
│ id (PK)     │
│ asset_id (FK)
│ asset_ip    │
│ port        │
│ protocol    │
│ state       │
│ service     │
│ ...         │
└─────────────┘

┌─────────────┐
│ SyncTask    │
│─────────────│
│ id (PK)     │
│ sync_type   │
│ status      │
│ total_count │
│ created_count
│ ...         │
└─────────────┘
```

### 主要数据表说明

#### 1. `soc_users` - 用户表
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | Integer | 主键 |
| username | String(50) | 用户名（唯一） |
| password_hash | String(255) | 密码哈希 |
| email | String(100) | 邮箱（唯一） |
| full_name | String(100) | 全名 |
| nick_name | String(100) | 昵称 |
| phone | String(20) | 电话 |
| avatar | String(255) | 头像 URL |
| status | String(20) | 状态（active/locked/disabled） |
| role_id | Integer | 角色 ID（外键） |
| department_id | BigInteger | 部门 ID（外键） |
| is_superuser | Boolean | 是否超级管理员 |
| last_login | DateTime | 最后登录时间 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### 2. `soc_assets` - 资产表
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | UUID | 主键 |
| network_segment | String(50) | 网络分段 |
| network_zone | String(50) | 网络区域 |
| asset_ip | Text | 资产 IP |
| name | String(255) | 资产名称 |
| asset_description | Text | 资产描述 |
| asset_type | String(50) | 资产类型 |
| criticality | String(20) | 重要程度 |
| asset_status | String | 资产状态 |
| data_source | String(20) | 数据来源 |
| wazuh_agent_id | String(100) | Wazuh Agent ID |
| owner | String(255) | 负责人 |
| business_unit | String(255) | 业务单元 |
| data_classification | String(20) | 数据分类 |
| owner_contact | String(50) | 负责人联系电话 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

**约束**: `(network_segment, asset_ip)` 唯一

#### 3. `soc_asset_ports` - 资产端口表
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | UUID | 主键 |
| asset_id | UUID | 资产 ID（外键） |
| asset_ip | INET | 资产 IP |
| port | Integer | 端口号 |
| protocol | String(10) | 协议（tcp/udp） |
| state | String(20) | 状态（open/closed/filtered） |
| service | String(100) | 服务名称 |
| version | Text | 服务版本 |
| service_banner | Text | 服务 banner |
| vulnerability | Text | 漏洞信息 |
| scan_time | DateTime | 扫描时间 |
| last_seen | DateTime | 最后发现时间 |
| created_at | DateTime | 创建时间 |

**约束**: `(asset_ip, port, protocol)` 唯一

#### 4. `soc_roles` - 角色表
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | Integer | 主键 |
| code | String(50) | 角色编码 |
| name | String(100) | 角色名称 |
| description | Text | 描述 |
| is_active | Boolean | 是否激活 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### 5. `soc_menus` - 菜单表
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | Integer | 主键 |
| parent_id | Integer | 父菜单 ID |
| name | String(100) | 菜单名称 |
| path | String(200) | 路由路径 |
| component | String(200) | 组件路径 |
| icon | String(100) | 图标 |
| sort | Integer | 排序 |
| is_hidden | Boolean | 是否隐藏 |
| keep_alive | Boolean | 是否缓存 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### 6. `soc_audit_logs` - 审计日志表
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | BigInteger | 主键 |
| user_id | Integer | 用户 ID（外键） |
| username | String(50) | 用户名 |
| action | String(50) | 操作类型 |
| resource_type | String(50) | 资源类型 |
| resource_id | String(255) | 资源 ID |
| resource_name | String(255) | 资源名称 |
| old_values | JSONB | 旧值 |
| new_values | JSONB | 新值 |
| ip_address | String(50) | IP 地址 |
| user_agent | String(500) | User Agent |
| status | String(20) | 状态 |
| error_message | Text | 错误信息 |
| created_at | DateTime | 创建时间 |

#### 7. `soc_sync_tasks` - 同步任务表
| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | UUID | 主键 |
| sync_type | String(50) | 同步类型 |
| status | String(20) | 状态（running/completed/failed） |
| total_count | Integer | 总数 |
| created_count | Integer | 创建数 |
| updated_count | Integer | 更新数 |
| failed_count | Integer | 失败数 |
| error_message | Text | 错误信息 |
| started_at | DateTime | 开始时间 |
| completed_at | DateTime | 完成时间 |

---

## API 接口文档

### API 通用信息
- **Base URL**: `/api/v1`
- **认证方式**: Bearer Token (JWT)
- **响应格式**: 统一响应包装

### 认证接口

#### 1. 获取验证码
```http
GET /auth/captcha
```
**响应**:
```json
{
  "captcha_key": "string",
  "captcha_image": "base64 string"
}
```

#### 2. 用户登录
```http
POST /auth/login
Content-Type: application/json

{
  "username": "string",
  "password": "string",
  "captcha_key": "string (optional)",
  "captcha_code": "string (optional)"
}
```
**响应**:
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer",
  "expires_in": 7200,
  "user": {
    "id": 1,
    "username": "string",
    "email": "string",
    "full_name": "string",
    "role_id": 1,
    "role_name": "string",
    "is_admin": true,
    "status": "active",
    "last_login": "2024-01-01T00:00:00Z"
  }
}
```

#### 3. 刷新 Token
```http
POST /auth/refresh
Content-Type: application/json

{
  "refresh_token": "string"
}
```

#### 4. 用户登出
```http
POST /auth/logout
Authorization: Bearer <token>
```

#### 5. 获取当前用户信息
```http
GET /auth/me
Authorization: Bearer <token>
```

---

### 资产管理接口

#### 1. 获取资产列表
```http
GET /assets?skip=0&limit=100&asset_type=server&criticality=high
Authorization: Bearer <token>
```
**查询参数**:
- `skip`: 跳过数量（默认 0）
- `limit`: 返回数量（默认 100，最大 1000）
- `asset_type`: 资产类型筛选
- `criticality`: 重要程度筛选
- `asset_status`: 资产状态筛选
- `network_zone`: 网络区域筛选

**响应**:
```json
{
  "items": [
    {
      "id": "uuid",
      "name": "string",
      "asset_ip": "string",
      "asset_type": "string",
      "criticality": "string",
      "owner": "string",
      "business_unit": "string",
      "asset_description": "string",
      "mac_address": "string",
      "wazuh_agent_id": "string",
      "asset_status": "string",
      "network_segment": "string",
      "network_zone": "string",
      "created_at": "datetime",
      "updated_at": "datetime",
      "status_updated_at": "datetime",
      "parent_id": "string"
    }
  ],
  "total": 100,
  "skip": 0,
  "limit": 100
}
```

#### 2. 获取资产概览
```http
GET /assets/overview
Authorization: Bearer <token>
```
**响应** 包含 KPI、分布图、24h 告警趋势、Top 表等聚合数据。

#### 3. 获取单个资产详情
```http
GET /assets/{asset_id}
Authorization: Bearer <token>
```

#### 4. 获取资产安全摘要
```http
GET /assets/{asset_id}/summary
Authorization: Bearer <token>
```

#### 5. 创建资产
```http
POST /assets
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "string",
  "network_segment": "string",
  "network_zone": "string",
  "asset_ip": "string",
  "asset_type": "string",
  "criticality": "string",
  "owner": "string",
  "business_unit": "string",
  "asset_description": "string",
  "mac_address": "string",
  "wazuh_agent_id": "string",
  "asset_status": "string",
  "data_classification": "string",
  "owner_contact": "string"
}
```

#### 6. 更新资产
```http
PUT /assets/{asset_id}
Authorization: Bearer <token>
Content-Type: application/json

{
  "name": "string",
  "asset_type": "string",
  "criticality": "string",
  "owner": "string",
  "business_unit": "string",
  "asset_description": "string",
  "asset_status": "string",
  "data_classification": "string",
  "owner_contact": "string"
}
```

#### 7. 删除资产
```http
DELETE /assets/{asset_id}
Authorization: Bearer <token>
```

#### 8. 从 Wazuh 同步资产
```http
POST /assets/sync/from-wazuh
Authorization: Bearer <token>
```
**响应**:
```json
{
  "message": "同步任务已创建",
  "task_id": "uuid",
  "status": "running"
}
```

---

### 端口管理接口

#### 1. 获取资产端口列表
```http
GET /assets/{asset_id}/ports?skip=0&limit=100
Authorization: Bearer <token>
```

#### 2. 添加资产端口
```http
POST /assets/{asset_id}/ports
Authorization: Bearer <token>
Content-Type: application/json

{
  "asset_ip": "string",
  "port": 80,
  "protocol": "tcp",
  "state": "open",
  "service": "http",
  "version": "string",
  "service_banner": "string",
  "vulnerability": "string"
}
```

#### 3. 更新资产端口
```http
PUT /assets/ports/{port_id}
Authorization: Bearer <token>
```

#### 4. 删除资产端口
```http
DELETE /assets/ports/{port_id}
Authorization: Bearer <token>
```

---

### 其他主要接口

#### 用户管理 (`/users`)
- `GET /users` - 获取用户列表
- `GET /users/{id}` - 获取用户详情
- `POST /users` - 创建用户
- `PUT /users/{id}` - 更新用户
- `DELETE /users/{id}` - 删除用户

#### 角色管理 (`/roles`)
- `GET /roles` - 获取角色列表
- `POST /roles` - 创建角色
- `PUT /roles/{id}` - 更新角色
- `DELETE /roles/{id}` - 删除角色

#### 菜单管理 (`/menus`)
- `GET /menus` - 获取菜单树
- `POST /menus` - 创建菜单
- `PUT /menus/{id}` - 更新菜单
- `DELETE /menus/{id}` - 删除菜单

#### 部门管理 (`/departments`)
- `GET /departments` - 获取部门树
- `POST /departments` - 创建部门
- `PUT /departments/{id}` - 更新部门
- `DELETE /departments/{id}` - 删除部门

#### 审计日志 (`/audit-logs`)
- `GET /audit-logs` - 获取审计日志列表

#### 系统配置 (`/system-configs`)
- `GET /system-configs` - 获取系统配置
- `PUT /system-configs` - 更新系统配置

---

## 依赖关系

### 后端依赖 ([requirements.txt](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/requirements.txt))
| 依赖包 | 版本 | 用途 |
|--------|------|------|
| fastapi | 0.115.0 | Web 框架 |
| uvicorn[standard] | 0.32.0 | ASGI 服务器 |
| pydantic | 2.10.1 | 数据验证 |
| pydantic-settings | 2.6.0 | 配置管理 |
| sqlalchemy | 2.0.36 | ORM |
| psycopg2-binary | >=2.9.9, <3.0.0 | PostgreSQL 驱动 |
| asyncpg | 0.30.0 | 异步 PostgreSQL 驱动 |
| python-jose[cryptography] | 3.3.0 | JWT 认证 |
| passlib[bcrypt] | 1.7.4 | 密码哈希 |
| python-multipart | 0.0.12 | 表单数据解析 |
| httpx | 0.27.2 | 异步 HTTP 客户端 |
| requests | 2.32.3 | HTTP 客户端 |
| zhipuai | >=2.1.5 | 智谱 AI SDK |
| python-dotenv | 1.0.1 | 环境变量管理 |
| loguru | 0.7.2 | 日志库 |
| python-dateutil | 2.9.0 | 日期时间工具 |

### 前端依赖 ([package.json](file:///Users/xiejava/AIProject/AI-miniSOC/src/frontend/package.json))

#### 生产依赖
| 依赖包 | 版本 | 用途 |
|--------|------|------|
| vue | ^3.5.26 | 前端框架 |
| vue-router | ^4.6.4 | 路由管理 |
| pinia | ^3.0.4 | 状态管理 |
| element-plus | ^2.13.0 | UI 组件库 |
| @element-plus/icons-vue | ^2.3.2 | Element Plus 图标 |
| axios | ^1.13.2 | HTTP 客户端 |
| echarts | ^6.0.0 | 图表库 |
| @vueuse/core | ^13.9.0 | Vue 组合式工具库 |
| pinia-plugin-persistedstate | ^4.7.1 | 状态持久化 |
| mitt | ^3.0.1 | 事件总线 |

#### 开发依赖
| 依赖包 | 版本 | 用途 |
|--------|------|------|
| typescript | ~5.6.3 | TypeScript |
| vite | ^7.3.0 | 构建工具 |
| @vitejs/plugin-vue | ^6.0.3 | Vue Vite 插件 |
| eslint | ^9.39.2 | 代码检查 |
| prettier | ^3.7.4 | 代码格式化 |
| stylelint | ^16.26.1 | 样式检查 |
| husky | ^9.1.7 | Git hooks |
| commitizen | ^4.3.1 | Git commit 规范化 |
| cz-git | ^1.12.0 | Git commit 适配器 |

### 外部服务依赖
| 服务 | 版本 | 用途 |
|------|------|------|
| PostgreSQL | 12+ | 主数据库 |
| Wazuh | 4.x | SIEM 系统 |
| Loki | 2.x | 日志存储 |
| Grafana | 10.x | 数据可视化 |
| OpenSearch | 2.x | 搜索引擎 |

---

## 项目运行方式

### 环境要求
- Python 3.10+
- Node.js 18+
- pnpm 8.8+
- PostgreSQL 12+
- Docker & Docker Compose（可选）

### 后端启动

#### 1. 配置环境变量
```bash
cd src/backend
cp .env.example .env
# 编辑 .env 文件，填入实际配置
```

**必需配置项**:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=AI-miniSOC-db
DB_USER=postgres
DB_PASSWORD=your_password

SECRET_KEY=your_secret_key_here
ENCRYPTION_KEY=your_encryption_key_here

GLM_API_KEY=your_glm_api_key
GLM_MODEL=glm-4-flash

WAZUH_API_URL=https://your-wazuh:55000
WAZUH_API_USERNAME=wazuh
WAZUH_API_PASSWORD=your_wazuh_password
```

#### 2. 安装依赖
```bash
cd src/backend
pip install -r requirements.txt
```

#### 3. 初始化数据库
```bash
# 使用 Alembic 迁移
alembic upgrade head

# 或运行初始化脚本
python scripts/init_system_data.py
```

#### 4. 启动后端服务
```bash
# 开发模式（自动重载）
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# 或使用启动脚本
./start.sh
```

#### 5. 访问 API 文档
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

---

### 前端启动

#### 1. 安装依赖
```bash
cd src/frontend
pnpm install
```

#### 2. 配置环境变量
```bash
# 创建 .env.development.local
cp .env.example .env.development.local
```

#### 3. 启动开发服务器
```bash
pnpm dev
```

#### 4. 访问应用
- 开发环境: http://localhost:5173

#### 5. 生产构建
```bash
pnpm build
# 预览构建结果
pnpm serve
```

---

### Docker 部署（可选）

#### 使用 Docker Compose 启动完整栈
```bash
docker-compose up -d
```

---

## 开发规范

### 后端开发规范

#### 1. 代码风格
- 遵循 PEP 8 规范
- 使用类型注解（Type Hints）
- 函数和类应有 docstring

#### 2. API 设计规范
- RESTful 风格
- 统一响应格式
- 使用合适的 HTTP 状态码
- 路径使用小写和连字符

#### 3. 数据库模型规范
- 继承 `Base` 基类
- 使用明确的表名前缀 `soc_`
- 定义必要的索引和约束
- 添加 `created_at` 和 `updated_at` 时间戳

#### 4. 测试规范
- 单元测试使用 pytest
- 测试文件放在 `tests/` 目录
- 使用独立的测试数据库

### 前端开发规范

#### 1. 代码风格
- 遵循 ESLint 规则
- 使用 TypeScript 类型定义
- 组件文件使用 `.vue` 扩展名
- 文件名使用 kebab-case

#### 2. 组件开发规范
- 组件名使用 PascalCase
- Props 定义使用 TypeScript 接口
- 使用 Composition API (`<script setup>`)
- 样式使用 scoped

#### 3. Git 提交规范
使用 commitizen 进行规范化提交：
```bash
pnpm commit
```

提交格式:
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Type 类型**:
- `feat`: 新功能
- `fix`: 修复 bug
- `docs`: 文档更新
- `style`: 代码格式
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建/工具相关

### 安全规范
1. 密码使用 bcrypt 哈希存储
2. 所有 API（除公开接口外）需要认证
3. 敏感操作记录审计日志
4. 使用 HTTPS 传输
5. 实现速率限制防止暴力攻击
6. Token 设置合理的过期时间

---

## 相关文档

- [项目 README](file:///Users/xiejava/AIProject/AI-miniSOC/README.md)
- [后端 README](file:///Users/xiejava/AIProject/AI-miniSOC/src/backend/README.md)
- [前端 README](file:///Users/xiejava/AIProject/AI-miniSOC/src/frontend/README.md)
- [架构设计文档](file:///Users/xiejava/AIProject/AI-miniSOC/docs/design/architecture.md)
- [数据库设计文档](file:///Users/xiejava/AIProject/AI-miniSOC/docs/design/database-design.md)

---

## 联系方式

- 作者: xiejava
- 项目地址: https://github.com/xiejava1018/AI-miniSOC

---

**文档版本**: 1.0
**最后更新**: 2026-06-06
