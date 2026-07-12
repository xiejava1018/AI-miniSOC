# AI-miniSOC

> AI 驱动的微型安全运营中心（Mini Security Operations Center） — 一个面向中小企业的轻量级、AI 增强的智能安全运营平台。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-active--development-orange.svg)](#项目状态)
[![Version](https://img.shields.io/badge/version-0.1.0--alpha-blue.svg)](#版本)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/vue-3.x-green.svg)](https://vuejs.org/)

---

## 📑 目录

- [项目概述](#项目概述)
- [核心功能](#核心功能)
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [快速开始](#快速开始)
- [配置说明](#配置说明)
- [Claude Code 技能](#claude-code-技能)
- [开发与测试](#开发与测试)
- [项目状态](#项目状态)
- [路线图](#路线图)
- [文档索引](#文档索引)
- [贡献指南](#贡献指南)
- [许可证](#许可证)

---

## 项目概述

AI-miniSOC 是一个**基于 AI 的轻量级安全运营平台**，集成了多种安全工具，提供智能化的安全监控、威胁检测和事件响应能力。

平台采用**前后端分离 + 容器化采集器**的现代化架构：

- **后端**：基于 FastAPI 的统一 API 网关，提供资产、告警、事件、用户、权限、AI 分析等核心能力。
- **前端**：基于 Vue 3 + Vite + TypeScript 的现代化管理控制台。
- **采集层**：基于 collector-framework 的容器化采集器，支持 Wazuh、TP-Link 等多数据源接入。
- **AI 层**：内置 Pi Agent、Art Bot、Agnes AI，支持自然语言日志查询、威胁分析、报告生成。
- **基础设施**：通过 Loki / OpenSearch / Wazuh / Prometheus / Grafana 打通日志聚合、检索、可视化链路。

> 🎯 **目标**：让中小企业用一台服务器就能跑起一个真正"会用 AI"的安全运营中心。

---

## 核心功能

### 1. 📊 日志聚合与分析
- **Loki** — 日志聚合系统（默认 7 天保留）
- **Grafana** — 可视化仪表板
- **OpenSearch** — 全文检索与日志分析
- **Filebeat / Otel** — 日志采集

### 2. 🛡️ 威胁检测与响应
- **Wazuh** — 主机入侵检测 + 安全信息与事件管理（SIEM）
- **告警引擎** — 实时告警与异常行为检测
- **规则引擎** — 自定义检测规则
- **事件管理** — 安全事件全生命周期跟踪（incidents / asset_incidents）

### 3. 💻 主机与网络监控
- **ops-health-check** — 系统健康检查（CPU / 内存 / 磁盘 / 负载）
- **容器监控** — Docker 容器状态
- **TP-Link 路由器采集器** — 自动发现内网资产与端口
- **Wazuh 采集器** — 自动同步 Wazuh agent 与资产信息

### 4. 💼 资产管理
- **资产台账** — 资产信息完整 CRUD
- **端口管理** — 资产端口批量管理与实时变更跟踪
- **Wazuh 同步** — 支持手动全量同步 + Webhook 实时同步（规则 504/506）
- **标签 / 业务单元** — 多维度分类
- **数据源溯源** — `data_source` 字段标记资产来源
- **同步历史** — 每次同步的统计信息、进度、字段级变更日志完整可审计
- **资产-事件关联** — 通过 asset_incidents 模块将安全事件与资产绑定

### 5. 🤖 AI 能力
- **Pi Agent** — AI 编排核心（已集成 POC）
- **Art Bot** — 智能体交互入口
- **Agnes AI** — 威胁分析 / 报告生成专用 AI
- **GLM (智谱)** — 大模型底座，配置见 `.env.example`
- **AI Chat / AI Agent API** — `/api/v1/ai/chat`、`/api/v1/ai/agent` 自然语言接口
- **趋势预测** — 安全威胁趋势分析
- **自然语言查询** — 用中文查询日志、告警、资产

### 6. 👥 用户与权限
- **RBAC** — 基于角色的访问控制（roles / users / menus）
- **认证** — JWT + 刷新令牌 + 验证码 + 黑名单机制
- **审计日志** — 完整操作审计 (`audit_logs`)
- **系统配置** — 字典 / 菜单 / 通知渠道动态配置

### 7. 🔔 通知与集成
- **多渠道通知** — 邮件 (SMTP) / 钉钉机器人 / 微信企业号
- **Webhook** — 接收 Wazuh / 第三方事件
- **告警通知** — 与告警引擎联动

---

## 系统架构

```
┌────────────────────────────────────────────────────────────────────┐
│                        Frontend (Vue 3 SPA)                        │
│            src/frontend  ──→  Vite + Pinia + Vue Router            │
└─────────────────────────────────┬──────────────────────────────────┘
                                  │ HTTP / WS
┌─────────────────────────────────▼──────────────────────────────────┐
│                    Backend API (FastAPI · async)                    │
│  src/backend/app/api    ──→  assets / alerts / incidents / auth    │
│                                ai / webhooks / ws / metrics …      │
└────┬──────────────┬──────────────┬──────────────┬─────────────────┘
     │              │              │              │
┌────▼─────┐  ┌─────▼──────┐ ┌─────▼──────┐ ┌────▼──────────┐
│PostgreSQL│  │   Redis    │ │  AI Layer  │ │  Observability │
│  资产    │  │  缓存/会话 │ │ Pi / Art / │ │ Prometheus /  │
│  告警    │  │            │ │  Agnes     │ │  OpenTelemetry│
│  审计    │  │            │ │  GLM 底座  │ │               │
└──────────┘  └────────────┘ └────────────┘ └───────────────┘

┌────────────────────────────────────────────────────────────────────┐
│                  Collectors (Docker · collector-framework)          │
│   wazuh-collector     ──→  Wazuh SIEM                              │
│   tplink-collector    ──→  TP-Link 路由器 (内网资产)               │
└────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────┐
│            Infra: Wazuh · Loki · Grafana · OpenSearch               │
│                       (通过 docker / compose 编排)                  │
└────────────────────────────────────────────────────────────────────┘
```

---

## 技术栈

| 层 | 技术 |
|---|---|
| **前端** | Vue 3 · Vite · TypeScript · Pinia · Vue Router · Element Plus · ECharts |
| **后端** | Python 3.11+ · FastAPI · SQLAlchemy (async) · Alembic · Pydantic v2 |
| **数据库** | PostgreSQL 14+ · Redis 6+ |
| **采集器** | Python (asyncio) · collector-framework · Docker |
| **AI / LLM** | Pi Agent · Art Bot · Agnes AI · GLM (智谱) · OpenAI 兼容接口 |
| **日志 / 监控** | Loki · OpenSearch · Grafana · Prometheus · OpenTelemetry |
| **安全** | Wazuh SIEM · Filebeat · Otel |
| **认证** | JWT · 刷新令牌 · RBAC · 验证码 |
| **CI / CD** | GitHub Actions (`.github/workflows/unit-tests.yml`、`e2e.yml`) |
| **部署** | Docker · Docker Compose · systemd unit（采集器） |
| **代码质量** | ESLint · Prettier · Stylelint · Husky · lint-staged · commitizen |

---

## 项目结构

```
AI-miniSOC/
├── src/
│   ├── backend/                # FastAPI 后端服务
│   │   ├── app/
│   │   │   ├── api/            # 路由：assets / alerts / ai / auth …
│   │   │   ├── core/           # 核心：config / security / permissions
│   │   │   ├── models/         # SQLAlchemy ORM
│   │   │   ├── schemas/        # Pydantic 数据契约
│   │   │   ├── services/       # 业务服务层
│   │   │   └── observability/  # 指标 / 链路追踪
│   │   ├── alembic/            # 数据库迁移
│   │   ├── migrations/         # 历史 SQL 迁移脚本
│   │   ├── scripts/            # 运维脚本
│   │   └── tests/              # pytest 集成 / 单元测试
│   ├── frontend/               # Vue 3 + Vite 前端
│   │   ├── src/
│   │   │   ├── views/          # 页面：asset / alert / auth / dashboard…
│   │   │   ├── components/     # 通用组件
│   │   │   ├── api/            # API 客户端封装
│   │   │   ├── store/          # Pinia 状态
│   │   │   └── router/         # 路由表
│   │   └── scripts/            # 构建 / 清理脚本
│   ├── collectors/             # 采集器（独立部署）
│   │   ├── base/               # collector-framework
│   │   ├── wazuh/              # Wazuh 采集器（Docker + systemd）
│   │   └── tplink/             # TP-Link 路由器采集器
│   └── agent-runner/           # Agent 运行器（实验性）
├── services/
│   └── wazuh-api-proxy/        # Wazuh API 代理
├── skills/                     # Claude Code 技能
│   ├── webdav-access/          # WebDAV 文件共享
│   ├── network-scan/           # 网络扫描
│   └── project-init/           # 项目初始化模板（minimal / standard / strict）
├── configs/
│   └── grafana/dashboards/     # Grafana 仪表板定义
├── scripts/
│   ├── install/install.sh      # 一键安装
│   ├── monitoring/             # 监控脚本
│   ├── database/               # 数据库初始化 / 迁移 SQL
│   └── poc/                    # PoC 脚本
├── docs/
│   ├── design/                 # 架构 / 功能设计（含 脆弱性管理 v0.2 / v1.0）
│   ├── development/            # 开发 & 排错指南、日报
│   ├── installation/           # 安装指南
│   ├── api/                    # API 文档
│   ├── plans/                  # 实施计划
│   ├── skills/                 # 技能文档
│   ├── superpowers/            # 高级主题
│   ├── code-wiki.md            # 代码知识库
│   ├── wazuh-integration-manual.md
│   └── wazuh配置.md            # Wazuh 中文配置
├── tests/integration/          # 跨服务集成测试
├── .github/workflows/          # CI：unit-tests / e2e
├── .env.example                # 环境变量样例
├── docker-compose.yaml         # （位于 src/collectors/）
├── CLAUDE.md                   # Claude Code 协作指南
├── CHANGELOG.md
├── SECURITY.md
└── README.md                   # ← 你正在看这里
```

---

## 快速开始

### 前置要求

| 组件 | 版本 / 要求 |
|---|---|
| Docker & Docker Compose | 最新稳定版 |
| PostgreSQL | 14+ |
| Redis | 6+ |
| Node.js | 18+ (前端开发) |
| pnpm | 最新稳定版 (前端) |
| Python | 3.11+ (本地开发) |
| 内存 | 8 GB+ |
| 磁盘 | 50 GB+ |
| OS | Linux 推荐 Ubuntu 22.04 / Debian 12 |

### 1. 克隆与初始化

```bash
git clone https://github.com/xiejava1018/AI-miniSOC.git
cd AI-miniSOC

# 复制环境变量样例并按需修改
cp .env.example .env

# 数据库准备（创建生产库 + 测试库）
psql -U postgres -c 'CREATE DATABASE "AI-miniSOC-db";'
psql -U postgres -c 'CREATE DATABASE "AI-miniSOC-db_test";'
```

### 2. 启动后端

```bash
cd src/backend
pip install -r requirements.txt
alembic upgrade head                  # 应用数据库迁移
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
# 健康检查：curl http://localhost:8000/api/v1/health
```

### 3. 启动前端

```bash
cd src/frontend
pnpm install
pnpm dev                              # 默认 http://localhost:5173
pnpm build                            # 生产构建
```

### 4. 启动采集器（Docker Compose）

```bash
cd src/collectors
# 确保 .env 中已配置 WAZUH_PASSWORD / ROUTER_PASSWORD / MINISOC_API_KEY
docker compose up -d
docker compose ps                     # 查看运行状态
docker compose logs -f wazuh-collector
```

### 5. 一键安装（可选）

```bash
./scripts/install/install.sh          # 自动部署 Wazuh / Loki / Grafana
```

### 访问入口

| 服务 | 地址 | 备注 |
|---|---|---|
| 前端 | http://localhost:5173 | 开发模式 |
| 后端 API | http://localhost:8000 | FastAPI |
| API 文档 (Swagger) | http://localhost:8000/docs | OpenAPI 3 |
| Grafana | http://192.168.0.30:3000 | admin / `.env` 中配置 |
| Wazuh | https://192.168.0.40:55000 | 默认账号 `wazuh-wui` |
| OpenSearch | https://192.168.0.30:9200 | 见 `.env` |
| Loki | http://192.168.0.30:3100 | 7 天保留 |

> 📌 默认基础设施部署在 `192.168.0.30 / 192.168.0.40`，如需修改请调整 `.env`。

---

## 配置说明

完整配置样例见 [`.env.example`](.env.example)。关键变量：

```bash
# 基础设施
LOKI_URL=http://192.168.0.30:3100
LOKI_RETENTION_DAYS=7
WAZUH_API_URL=https://192.168.0.40:55000
OPENSEARCH_URL=https://192.168.0.30:9200

# 数据库
DB_HOST=192.168.0.42
DB_NAME=AI-miniSOC-db
TEST_DB_NAME=AI-miniSOC-db_test      # 跑 pytest 前必须先创建

# AI / LLM
GLM_API_KEY=your_glm_api_key_here
GLM_MODEL=glm-4-flash
GLM_API_BASE=https://open.bigmodel.cn/api/paas/v4/

# 通知
SMTP_HOST=smtp.example.com
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=...
WECHAT_WEBHOOK=https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...

# 健康检查阈值（脚本中默认）
DISK_WARN=50  DISK_CRIT=80
MEM_WARN=70   MEM_CRIT=90
LOAD_WARN=2.0 LOAD_CRIT=5.0
```

Wazuh 集成详细步骤：[docs/wazuh-integration-manual.md](docs/wazuh-integration-manual.md) · [docs/wazuh配置.md](docs/wazuh配置.md)

---

## Claude Code 技能

AI-miniSOC 自带若干 Claude Code 技能，可在 [skills/](skills/) 中查看：

| 技能 | 状态 | 说明 |
|---|---|---|
| [webdav-access](skills/webdav-access/) | ✅ 稳定 | WebDAV 文件共享访问（上传/下载/目录/删除/自然语言） |
| [network-scan](skills/network-scan/) | ✅ 可用 | 内网主机与端口扫描 |
| [project-init](skills/project-init/) | ✅ 可用 | 项目脚手架初始化（minimal / standard / strict 三档模板） |

开发中：`log-query` · `threat-analysis` · `report-gen`

---

## 开发与测试

### 代码规范

- 前端：`pnpm lint`、`pnpm lint:prettier`、`pnpm lint:stylelint`
- 后端：遵循 PEP 8，使用 `ruff` / `black`（见 `pyproject.toml`）
- 提交：Husky + lint-staged + commitizen，提交信息遵循 Conventional Commits

### 运行测试

```bash
# 后端单元 + 集成测试
cd src/backend
pytest                                  # 全部
pytest tests/unit                       # 仅单元
pytest tests/integration                # 仅集成（需 TEST_DB_NAME）

# 前端单元测试
cd src/frontend
pnpm test

# E2E（GitHub Actions）
.github/workflows/e2e.yml
```

### CI

- 单元测试：[`.github/workflows/unit-tests.yml`](.github/workflows/unit-tests.yml)
- 端到端：[`.github/workflows/e2e.yml`](.github/workflows/e2e.yml)

---

## 项目状态

| 模块 | 状态 |
|---|---|
| 基础架构（Docker / Compose / systemd） | ✅ 完成 |
| Wazuh SIEM 集成 | ✅ 完成 |
| Loki 日志聚合 | ✅ 完成 |
| Grafana 可视化 | ✅ 完成 |
| 后端 API 框架（FastAPI + 异步 ORM） | ✅ 完成 |
| 前端管理控制台（Vue 3 + Element Plus） | ✅ 完成 |
| 用户 / 角色 / 认证 / 审计 | ✅ 完成 |
| 资产管理 CRUD + 端口管理 + 标签 | ✅ 完成 |
| Wazuh 资产同步（全量 + Webhook） | ✅ 完成 |
| Wazuh 采集器（Docker + systemd） | ✅ 完成 |
| TP-Link 采集器 | ✅ 完成 |
| ops-health-check 健康检查 | ✅ 完成 |
| WebDAV / 网络扫描 / 项目初始化技能 | ✅ 完成 |
| Pi Agent 集成 | ✅ POC 完成 |
| Agnes AI 威胁分析 / 报告生成 | ✅ 集成完成 |
| Art Bot 入口 | ✅ 改用 Pi Agent |
| AI 日志自然语言查询 | ✅ 完成 |
| 告警引擎与通知（邮件/钉钉/微信） | 🚧 进行中 |
| 事件响应与 SOAR | 📅 计划中 |
| 自动化剧本 / 工单系统 | 📅 计划中 |

---

## 路线图

### Phase 1：基础监控 ✅
- [x] 部署 Wazuh SIEM
- [x] 配置 Loki 日志聚合
- [x] 集成 Grafana 仪表板
- [x] 开发健康检查脚本
- [x] 采集器框架（collector-framework）

### Phase 2：AI 增强 ✅（核心完成）
- [x] Pi Agent 编排核心
- [x] Agnes AI 威胁分析
- [x] Art Bot 智能入口
- [x] 自然语言日志查询
- [x] 资产 AI 解读（实验性）

### Phase 3：自动化响应（进行中）
- [x] 多渠道通知（邮件 / 钉钉 / 微信）
- [x] Webhook 接入
- [ ] 告警去重 / 合并
- [ ] 自动化响应剧本（Playbook）
- [ ] SOAR 编排
- [ ] 工单系统集成

### Phase 4：规模与生态（计划）
- [ ] 集群化部署
- [ ] 多租户
- [ ] 威胁情报集成（TI Feed）
- [ ] 插件市场
- [ ] SaaS 控制台

---

## 文档索引

| 文档 | 路径 |
|---|---|
| Claude Code 协作指南 | [CLAUDE.md](CLAUDE.md) |
| 代码知识库 | [docs/code-wiki.md](docs/code-wiki.md) |
| 变更日志 | [CHANGELOG.md](CHANGELOG.md) |
| 安全策略 | [SECURITY.md](SECURITY.md) |
| 环境变量样例 | [.env.example](.env.example) |
| Wazuh 集成手册 | [docs/wazuh-integration-manual.md](docs/wazuh-integration-manual.md) |
| Wazuh 中文配置 | [docs/wazuh配置.md](docs/wazuh配置.md) |
| 设计文档 | [docs/design/](docs/design/) |
| 安装指南 | [docs/installation/](docs/installation/) |
| API 文档 | [docs/api/](docs/api/) |
| 实施计划 | [docs/plans/](docs/plans/) |

---

## 贡献指南

欢迎贡献！请阅读 [CLAUDE.md](CLAUDE.md) 了解本项目的协作约定，提交前请：

1. Fork 仓库并创建特性分支 (`git checkout -b feat/amazing-feature`)
2. 遵循代码规范 (`pnpm lint` / 后端 `ruff`)
3. 补充必要的测试用例
4. 使用 Conventional Commits 提交信息
5. 发起 Pull Request，并附上清晰的变更说明

安全相关问题请按 [SECURITY.md](SECURITY.md) 流程上报，请勿在公开 Issue 中披露。

---

## 许可证

本项目基于 [MIT License](LICENSE) 开源。

---

## 联系方式

- **作者**：xiejava
- **项目主页**：https://github.com/xiejava1018/AI-miniSOC
- **问题反馈**：https://github.com/xiejava1018/AI-miniSOC/issues
- **Wazuh 社区对接**：见 [docs/wazuh-integration-manual.md](docs/wazuh-integration-manual.md)

---

<sub>📅 最后更新：2026-07-12 · 🏷️ 版本 v0.1.0-alpha</sub>