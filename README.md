# AI-miniSOC

> **AI 驱动的微型安全运营中心**（Mini Security Operations Center）—— 一个面向中小企业的轻量级、AI 增强的智能安全运营平台。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-active--development-orange.svg)](#项目状态)
[![Version](https://img.shields.io/badge/version-2.4-blue.svg)](#版本)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/vue-3.5-green.svg)](https://vuejs.org/)

---

## 📑 目录

- [项目概述](#项目概述)
- [核心功能](#核心功能)
- [系统架构](#系统架构)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [生产部署拓扑](#生产部署拓扑)
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

AI-miniSOC 是一个**面向中小企业的轻量级 AI 安全运营中心**，将日志聚合、威胁检测、资产稽核、攻击面扫描与 AI 解读能力整合在一个可单机 / 小集群部署的平台里。

平台采用**前后端分离 + 容器化采集器**的现代化架构：

- **后端**：基于 FastAPI 的统一 API 网关（**52 张业务表 · 43 个 API 路由 · 60+ 服务**），提供资产、告警、事件、用户、权限、AI 分析、报告、稽核、攻击面扫描等核心能力。
- **前端**：基于 Vue 3 + Vite + TypeScript + Element Plus 的现代化管理控制台，含 11 个顶级菜单（概览 / 资产 / 脆弱性 / 事件 / 告警 / 上网行为 / 安全报告 / 运维管理 / 资产管理 / 系统管理 / 扫描等）。
- **采集层**：基于 `collector-framework` 的容器化采集器，支持 **Wazuh**（agent / SCA / SCAP）、**TP-Link**（路由器内网资产）、**Nmap 攻击面扫描器**（拉模型，控制面/数据面分离）三类数据源。
- **AI 层**：以智谱 GLM 为统一大模型底座，覆盖 7 个 AI 消费点：自然语言资产查询（L1+L2）、风险摘要、变更影响分析、AI 安全报告、对账 AI 解读、合规 AI 解读、AI Chat；全部具备**诚实降级**路径。
- **基础设施**：Loki（7 天日志保留）+ Wazuh SIEM + OpenSearch（告警 / 脆弱性）+ Grafana + PostgreSQL 16。

> 🎯 **目标**：让中小企业用一台 8 GB 内存的小服务器就能跑起一个真正"会用 AI"的安全运营中心。

---

## 核心功能

### 1. 📊 日志聚合与分析
- **Loki** —— 日志聚合系统（默认 7 天保留，12000 小时最大查询窗口）
- **Grafana** —— 可视化仪表板（接入 Loki / OpenSearch / Prometheus）
- **OpenSearch** —— Wazuh 告警 / 脆弱性结构化存储（可水平扩展，承接告警与脆弱性数据）
- **OpenTelemetry** —— 路由器 syslog 经 OTLP 接入

### 2. 🛡️ 威胁检测与响应
- **Wazuh** —— 主机入侵检测 + SIEM（WebHook 实时同步 + 手动全量同步）
- **告警治理** —— 告警聚合 / 分级 / 治理配置 / 摘要生成
- **规则引擎** —— 自定义检测规则 + CISA KEV 已知漏洞库
- **事件管理** —— 安全事件全生命周期跟踪（`soc_incidents` / `soc_asset_incidents` 多对多）

### 3. 💻 主机与网络监控
- **ops-health-check** —— 系统健康检查（CPU / 内存 / 磁盘 / 负载 / 容器 / 服务）
- **TP-Link 路由器采集器** —— 自动发现内网资产 + 上网行为日志
- **Wazuh 采集器** —— 自动同步 agent / 资产 / SCA / SCAP 数据
- **攻击面扫描器**（Nmap）—— 控制面/数据面分离的拉模型，主动发现影子资产 + 公网暴露面

### 4. 💼 资产 & 攻击面管理
- **资产台账** —— 资产信息完整 CRUD，含 `data_source` / `source_id` 溯源字段
- **端口管理** —— 资产端口批量管理 + 实时变更跟踪 + `soc_asset_port_sources` 多源汇聚
- **资产稽核（F1.3）** —— `shadow` / `offline` / `mismatch` 三类差异，扫描器发现自动入稽核
- **Wazuh 同步** —— 手动全量 + Webhook 实时同步（504/506）
- **标签 / 业务单元** —— 多维度分类
- **数据健康** —— 源健康 / 同步死信 / 对账差异三层聚合
- **同步历史** —— 每次同步的统计、进度、字段级变更日志完整可审计

### 5. 🤖 AI 能力（GLM 统一底座）
7 个 AI 消费点 + 降级演练全部通过：

| 功能 | 入口 | 状态 |
|---|---|---|
| 自然语言资产查询 L1 | `POST /api/v1/assets/ask` | ✅ |
| 自然语言资产查询 L2（受限模板） | 同上（自动路由） | ✅ |
| 风险摘要 | `GET /risk/overview` AI 解读 | ✅ |
| AI 安全报告（F2.2） | `POST /reports/generate` | ✅ |
| 变更影响分析（F3.1） | `POST /assets/impact-analysis` | ✅ |
| 对账 AI 解读 | `GET /assets/reconciliation/{id}/ai-report` | ✅ |
| 合规 AI 解读 | `POST /compliance/{id}/interpret` | ✅ |
| AI Chat | `POST /api/v1/ai/chat` | ✅ |
| AI Agent | `POST /api/v1/ai/agent` | ✅ |

**W0 评测集**：`asset_query_eval.yaml` 50 条用例，基线准确率 **98%**，对抗样本 5/5 全拒。

### 6. 📋 安全报告与合规
- **AI 安全报告** —— weekly / monthly / on_demand / incident_driven 四种触发
- **合规基线** —— 内置 compliance_rules.yaml，AI 解读 + 规则模板降级
- **脆弱性管理** —— CISA KEV 自动同步 + SCA + SCAP 多源接入
- **资产详情 EOL** —— 生命周期管理 + operator 可手动覆盖

### 7. 👥 用户与权限（X1 权限矩阵）
- **RBAC** —— 角色 admin / operator / viewer / auditor 端点级隔离
- **认证** —— JWT + 刷新令牌 + 验证码 + 登录失败计数 + 自动锁定 + logout 黑名单 + refresh rotation
- **按钮级权限** —— `v-auth` 指令 + `useAuth()` Hook + `require_button_permission()` 后端依赖
- **审计日志** —— 全操作可审计（含 AI 消费、对账、EOL、报告生成）
- **系统配置** —— 字典 / 菜单 / 通知渠道动态配置

### 8. 🔔 通知与推送（F4.2 五场景）
- **多渠道通知** —— 邮件 (SMTP) / 钉钉机器人 / 微信企业号
- **主动推送 5 场景** —— 数据链路异常 / 评分突变 / EOL / 影子资产发现 / 报告生成完成
- **站内通知** —— WebSocket 实时推送
- **扫描器离线** —— 6th 场景（依赖 F1.3 影子资产发现）

---

## 系统架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                     Frontend (Vue 3 + Vite)                         │
│  src/frontend  ──→  Element Plus + Pinia + Vue Router              │
│  11 顶级菜单：概览 / 资产 / 脆弱性 / 事件 / 告警 / 上网行为 /       │
│              安全报告 / 运维管理 / 系统管理 / 扫描 / 配置            │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │ HTTP / WS
┌─────────────────────────────────▼───────────────────────────────────┐
│                Backend API (FastAPI · Python 3.13)                  │
│  src/backend/app/api  ──→  43 个路由模块                              │
│  services/        ──→  60+ 服务（含 AI / 对账 / 报告 / 影响分析）  │
│  models/          ──→  52 张 SQLAlchemy ORM 表 (统一 soc_ 前缀)    │
└────┬──────────────┬──────────────┬──────────────┬──────────────────┘
     │              │              │              │
┌────▼─────┐  ┌─────▼──────┐ ┌─────▼──────┐ ┌────▼──────────┐
│PostgreSQL│  │   AI Layer │ │ Observabil │ │ Notification  │
│   16     │  │  GLM (智谱) │ │  OpenTel   │ │ 邮件/钉钉/微信│
│  52 张表 │  │ + 7 消费点  │ │  Prometheus│ │  + WebSocket  │
│          │  │ + 诚实降级  │ │            │ │  + 站内通知   │
└──────────┘  └────────────┘ └────────────┘ └───────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│             Collectors (Docker · collector-framework)               │
│   wazuh-collector    ──→  Wazuh SIEM (agents / SCA / SCAP)         │
│   tplink-collector   ──→  TP-Link 路由器 (内网资产 + 上网行为)      │
│   scanner-collector  ──→  Nmap 攻击面扫描 (拉模型 · 控制面/数据面分离)│
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│              Infra: Wazuh · Loki · Grafana · OpenSearch             │
│                       (生产部署在内网私有网段，详见部署文档)        │
└─────────────────────────────────────────────────────────────────────┘
```

> **架构要点**：
> - 采集器只**出向请求**（心跳 + 拉任务 + 推数据），天然穿透 NAT
> - 扫描器显式注册：admin `POST /scan/agents` 分配 `scanner_id` + API Key
> - 7 个 AI 消费点全部走 GLM，单点可禁用 / 切换模型
> - 响应统一包装：`{code, msg, data}`，HTTP 恒 200，业务码在 `body.code`

---

## 技术栈

| 层 | 技术 | 版本 |
|---|---|---|
| **前端框架** | Vue | 3.5.26 |
| **前端构建** | Vite + TypeScript | Vite 7.3.0 / TS 5.6.3 |
| **前端 UI** | Element Plus + Tailwind CSS | Element Plus 2.13.0 / Tailwind 4.1.18 |
| **前端状态** | Pinia（持久化） + Vue Router | Pinia 3.0.4 / Router 4.6.4 |
| **前端图表** | ECharts | — |
| **前端基础** | art-design-pro-edge（已剥离多租户） | — |
| **后端框架** | Python + FastAPI（async） | Python 3.13 / FastAPI 0.141 |
| **后端 ORM** | SQLAlchemy（async） + asyncpg + psycopg2-binary | SQLAlchemy 2.0.36 |
| **后端校验** | Pydantic v2 + pydantic-settings | 2.13.4 / 2.15.0 |
| **后端迁移** | Alembic | 39 个迁移（head `u3v4w5x6y7z8`） |
| **后端认证** | PyJWT + passlib[bcrypt] + python-multipart | — |
| **数据库** | PostgreSQL | 16+（生产 16.15） |
| **采集器** | Python（asyncio） + httpx + collector-framework | Python 3.13 / httpx 0.28.1 |
| **AI / LLM** | 智谱 GLM（统一底座） + OpenAI 兼容接口 | glm-4-flash（默认） |
| **日志** | Loki + OpenSearch + Grafana | Loki 7 天保留 |
| **监控** | Prometheus + OpenTelemetry | — |
| **安全** | Wazuh SIEM | — |
| **MCP** | mcp（让 Agent 通过 MCP 调用 FastAPI） | >= 1.20（< 1.13 启动崩溃） |
| **CI/CD** | GitHub Actions + self-hosted runner | CI 4 个 workflow / CD `deploy-prod.yml` |
| **部署** | systemd（后端 `aisoc-backend`）+ nginx 8080（前端）+ Docker Compose（采集器） | — |

---

## 项目结构

```
AI-miniSOC/
├── src/
│   ├── backend/                    # FastAPI 后端（Python 3.13）
│   │   ├── app/
│   │   │   ├── api/                # 43 个路由模块（auth / users / roles / menus / 
│   │   │   │                      #   assets / asset_ports / asset_tags / 
│   │   │   │                      #   asset_incidents / asset_reconciliation /
│   │   │   │                      #   asset_risk / asset_query / asset_lifecycle /
│   │   │   │                      #   impact_analysis / asset_summary / …
│   │   │   │                      #   alerts / alert_digests / browsing /
│   │   │   │                      #   compliance / sca / vulnerabilities /
│   │   │   │                      #   incidents / data_sync / sync /
│   │   │   │                      #   data_health / reports / ai / ai_agent /
│   │   │   │                      #   ai_chat / ai_feedback / scan_* /
│   │   │   │                      #   knowledge / departments / dicts /
│   │   │   │                      #   system_configs / audit_logs /
│   │   │   │                      #   webhooks / ws / public / dashboard /
│   │   │   │                      #   metrics / task_observability /
│   │   │   │                      #   notifications / deps）
│   │   │   ├── core/               # config / security / permissions / response_wrapper
│   │   │   │                      # alert_levels / deps
│   │   │   ├── models/             # SQLAlchemy ORM（52 张表，统一 soc_ 前缀）
│   │   │   ├── schemas/            # Pydantic 数据契约
│   │   │   ├── services/           # 60+ 业务服务（含 sync_handlers/、
│   │   │   │                      #   opensearch/、task_observability/、
│   │   │   │                      #   browsing_detection/）
│   │   │   ├── observability/      # Prometheus 指标 / OpenTelemetry
│   │   │   └── mcp/                # MCP（Model Context Protocol）集成
│   │   ├── alembic/                # 数据库迁移（39 个迁移，head `u3v4w5x6y7z8`）
│   │   ├── tests/                  # 单元 / 集成测试（in-process）
│   │   └── main.py                 # FastAPI 入口（lifespan 注册所有 scheduler）
│   │
│   ├── frontend/                   # Vue 3 + Vite 前端（art-design-pro-edge）
│   │   ├── src/
│   │   │   ├── api/                # API 客户端封装（含 scan / asset / report）
│   │   │   ├── components/         # 通用组件 + 业务组件
│   │   │   ├── composables/        # 组合式函数
│   │   │   ├── config/             # 应用配置
│   │   │   ├── constants/          # 常量（路由别名等）
│   │   │   ├── directives/         # 自定义指令（v-auth）
│   │   │   ├── hooks/              # useTable / useAuth / useSystem 等
│   │   │   ├── enums/              # TypeScript 枚举
│   │   │   ├── router/             # 路由（后端驱动菜单）
│   │   │   ├── store/              # Pinia（持久化）
│   │   │   ├── types/              # TypeScript 类型
│   │   │   ├── utils/              # 工具函数
│   │   │   └── views/              # 页面（11 顶级菜单 + 配置 + 占位）
│   │   │       ├── asset/          #   /asset/{list,detail,overview,reconciliation,
│   │   │       │                  #       data-health,compliance,impact-analysis}
│   │   │       ├── alert/          #   /alert/*
│   │   │       ├── browsing/       #   /browsing/*
│   │   │       ├── incidents/      #   /incidents/list
│   │   │       ├── vulnerability/  #   /vulnerability/*
│   │   │       ├── reports/        #   /reports/list
│   │   │       ├── knowledge/      #   /knowledge/*
│   │   │       ├── scan/           #   /scan/{scanners,tasks,findings,targets}
│   │   │       ├── dashboard/      #   /dashboard/console
│   │   │       ├── system/         #   /system/{user,role,menu,department,
│   │   │       │                  #           dict,config,audit-log}
│   │   │       └── ops/            #   /ops/{task-center,impact-analysis,
│   │   │                          #       data-health,knowledge}
│   │   ├── scripts/                # 构建脚本
│   │   └── vite.config.ts
│   │
│   ├── collectors/                 # 采集器（独立部署）
│   │   ├── base/                   # collector-framework 共享库
│   │   ├── tplink/                 # TP-Link 路由器资产采集器
│   │   ├── wazuh/                  # Wazuh SIEM 采集器（Docker + systemd）
│   │   ├── scanner/                # 攻击面扫描采集器（Nmap + 控制面/数据面分离）
│   │   ├── run_daemon.py           # 旧守护逻辑（建议评估删除）
│   │   └── docker-compose.yaml
│   │
├── deploy/                          # 生产部署
│   ├── deploy.sh                   # 应用部署（fetch + pip + vite build + 
│   │                              #   systemd restart + 自动回滚）
│   ├── deploy_collectors.sh        # 采集器部署（含健康门禁 + 僵尸进程核查）
│   ├── aisoc-backend.service       # systemd unit（生产用，替代 nohup）
│   ├── aisoc-deployer.sudoers      # sudoers NOPASSWD 最小权限
│   ├── actions-runner.service      # GitHub Actions runner unit
│   └── db_healthcheck.py           # 部署后 DB 探活
│
├── configs/                        # 配置文件
│   ├── compliance_rules.yaml       # 合规基线规则
│   ├── query_templates.yaml        # L2 复合查询模板（4 个）
│   ├── eval/asset_query_eval.yaml  # W0 评测集（50 条）
│   ├── grafana/dashboards/         # Grafana 仪表板
│   └── prometheus/                 # Prometheus 配置
│
├── scripts/                        # 工具脚本
│   ├── eval_asset_query.py         # W0 评测脚本（基线 98%）
│   ├── install/                    # 一键安装（Wazuh / Loki / Grafana）
│   ├── database/                   # 数据库初始化 / 迁移 SQL
│   ├── monitoring/                 # 监控脚本
│   ├── poc/                        # PoC 脚本
│   ├── security-check.sh
│   ├── test-integration.sh
│   └── wazuh-*.sh / wazuh-add-grafana-user.py
│
├── docs/                           # 项目文档（45 份设计 + 部署 + Runbook）
│   ├── design/                     # 架构 / 功能设计 / 评审报告
│   ├── development/                # 开发 & 排错指南 / 日报 / cicd.md
│   ├── installation/               # 安装指南
│   ├── api/                        # API 文档
│   ├── plans/                      # 实施计划
│   ├── runbook/                    # 运维 Runbook
│   ├── operations/                 # 运维手册
│   ├── superpowers/                # 高级主题
│   ├── skills/                     # 技能文档
│   ├── code-wiki.md                # 代码知识库
│   ├── wazuh-integration-manual.md
│   └── wazuh配置.md
│
├── skills/                         # Claude Code 技能
│   ├── webdav-access/              # WebDAV 文件共享
│   ├── network-scan/               # 网络扫描
│   └── project-init/               # 项目初始化模板（minimal / standard / strict）
│
├── openspec/                       # OpenSpec 变更管理
│
├── .github/workflows/              # CI/CD
│   ├── ci-backend.yml              # 后端 CI（lint + pytest）
│   ├── ci-frontend.yml             # 前端 CI（lint + build）
│   ├── unit-tests.yml              # 单元测试
│   ├── e2e.yml                     # E2E（已禁用）
│   └── deploy-prod.yml             # CD：CI 成功 → self-hosted runner → 102
│
├── .env.example                    # 环境变量样例
├── CLAUDE.md                       # Claude Code 协作指南（v2.24，含全部历史决策）
├── CHANGELOG.md
├── SECURITY.md
└── README.md                       # ← 你正在看这里
```

---

## 生产部署拓扑

> ⚠️ **公开 README 仅描述架构形态**——具体 IP、主机名、网段规划属于部署方私有信息，不在仓库中公开。

```
┌─────────────────────────────────────────────────────────────────┐
│  GitHub (github.com/xiejava1018/AI-miniSOC)                     │
│    push master → CI (Backend + Frontend + UnitTests)            │
└──────────────────────────────────┬──────────────────────────────┘
                                   │ CI 全绿触发 workflow_run
┌──────────────────────────────────▼──────────────────────────────┐
│  生产服务器（内网私有网段）                                       │
│  ───────────────────────────────────────────────────────────── │
│  - self-hosted runner: aisoc-prod-deployer                       │
│  - 后端: systemd aisoc-backend（FastAPI 默认 :8000）             │
│  - 前端: nginx :8080 服务 dist/                                  │
│  - DB: PostgreSQL 16.x 同机部署                                  │
│       生产库 AI-miniSOC-db                                       │
│  - 部署脚本: deploy/deploy.sh                                    │
│    fetch(depth+timeout) → npm ci → pip → vite build →           │
│    systemctl restart → HTTP+DB 双探活 → 失败全局 trap 回滚       │
│  - sudoers: NOPASSWD 10 条最小权限，deploy 无人值守              │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
       ┌───────────────────────────┼───────────────────────────┐
       │                           │                           │
┌──────▼──────┐            ┌───────▼────────┐         ┌───────▼────────┐
│ 同机        │            │ 基础设施机 A   │         │ 基础设施机 B   │
│ /var/log/   │            │ Wazuh Manager  │         │ Wazuh Indexer  │
│ aisoc/      │            │ Loki           │         │ OpenSearch     │
│             │            │ Grafana        │         │                │
└─────────────┘            └────────────────┘         └────────────────┘

┌─────────────────────────────────────────┐
│ 扫描器节点（任意内网主机）                │
│   scanner-collector 常驻拉模型          │
│   nmap + python3 + collector-framework   │
│   30s 心跳 + 10s 拉任务                 │
└─────────────────────────────────────────┘
```

**三层库分离（绝不可混）**：

| 库 | 用途 | 位置 |
|---|---|---|
| `AI-miniSOC-db` | 生产 | 生产服务器本机 |
| `AI-miniSOC-testdb` | 本地 dev | 本机 |
| `AI-miniSOC-db_test` | pytest 专用 | 本机（跑测试前必须 `CREATE DATABASE`） |

> ⚠️ **本地 `.env` 绝不指向生产库**——CI/CD 的 `git reset --hard` 不会改 `.env`（gitignore），
> 但本地手工编辑会；发版前请确认 `DB_HOST` 指向正确环境。

详见 [`docs/development/cicd.md`](docs/development/cicd.md)（v2.7，含 CI/CD 全部演进）。

---

## 快速开始

### 前置要求

| 组件 | 版本 / 要求 |
|---|---|
| Docker & Docker Compose | 最新稳定版 |
| PostgreSQL | 16+（生产实测 16.15） |
| Node.js | 18+（前端开发） |
| npm | 9+（前端，**不**用 pnpm） |
| Python | **3.13**（本地开发，venv 已固定） |
| 内存 | 8 GB+ |
| 磁盘 | 50 GB+ |
| OS | Linux 推荐 Ubuntu 22.04 / Debian 12 / macOS |

### 1. 克隆与初始化

```bash
git clone https://github.com/xiejava1018/AI-miniSOC.git
cd AI-miniSOC

# 复制环境变量样例并按需修改
cp .env.example .env

# 数据库准备（必须创建三个库，绝不混用）
psql -U postgres -c 'CREATE DATABASE "AI-miniSOC-db";'         # 生产
psql -U postgres -c 'CREATE DATABASE "AI-miniSOC-testdb";'      # 本地 dev
psql -U postgres -c 'CREATE DATABASE "AI-miniSOC-db_test";'     # pytest 专用
```

> 💡 `DB_NAME` 环境变量可覆盖 `.env` 的 `DB_NAME`（pydantic-settings env 优先）：
> `DB_NAME=AI-miniSOC-db_test ../../venv/bin/python -m alembic -c alembic.ini upgrade head`

### 2. 启动后端

```bash
cd src/backend
# 必须从 src/backend/ 启动才能正确加载 .env
../../venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 健康检查
curl http://localhost:8000/api/v1/health
```

### 3. 启动前端

```bash
cd src/frontend
npm install
npm run dev       # 开发服务器: http://localhost:3006
# 生产构建（vue-tsc 必挂，用 `npx vite build`）：
npx vite build
```

### 4. 启动采集器（Docker Compose）

```bash
cd src/collectors
# 三个 service：tplink-collector / wazuh-collector / scanner-collector
docker compose up -d
docker compose ps
docker compose logs -f scanner-collector
```

`.env` 必须注入：`MINISOC_API_KEY` / `WAZUH_PASSWORD` / `ROUTER_PASSWORD` / `SCANNER_ID`（注册后由控制面下发）。

### 5. 一键安装（可选）

```bash
./scripts/install/install.sh          # 自动部署 Wazuh / Loki / Grafana
```

### 访问入口

| 服务 | 地址 | 备注 |
|---|---|---|
| 前端（dev） | http://localhost:3006 | Vite 开发服务器 |
| 后端 API | http://localhost:8000 | FastAPI |
| API 文档 (Swagger) | http://localhost:8000/docs | OpenAPI 3 |
| Grafana | `GRAFANA_URL`（见 `.env`） | `.env` 中配置 |
| Wazuh Dashboard | `WAZUH_DASHBOARD_URL` | wazuh-wui 用户 |
| Wazuh API | `WAZUH_API_URL` | JWT 认证 |
| OpenSearch | `OPENSEARCH_URL` | 见 `OPENSEARCH_PASSWORD` |
| Loki | `LOKI_URL` | 默认 7 天保留，12000h 最大查询 |

> 📌 所有基础设施地址通过 `.env` 注入，部署到不同环境只需修改对应变量值。
> 后端 .env 的键名必须与 `app.core.config.Settings` 字段 1:1 对应。

---

## 配置说明

完整配置样例见 [`.env.example`](.env.example)。关键分组：

```bash
# 基础设施
LOKI_URL=http://<loki-host>:<port>
LOKI_RETENTION_DAYS=7
WAZUH_API_URL=https://<wazuh-host>:<port>
WAZUH_API_USERNAME=your_wazuh_username
WAZUH_API_PASSWORD=your_wazuh_password
OPENSEARCH_URL=https://<opensearch-host>:<port>
OPENSEARCH_USER=your_opensearch_user
OPENSEARCH_PASSWORD=your_opensearch_password

# 数据库（生产）
DB_HOST=your_production_db_host   # 生产服务器内网地址
DB_PORT=5432
DB_NAME=AI-miniSOC-db
TEST_DB_NAME=AI-miniSOC-db_test      # pytest 跑前必须先 CREATE DATABASE

# AI / LLM（统一底座）
GLM_API_KEY=your_glm_api_key_here
GLM_MODEL=glm-4-flash
GLM_API_BASE=https://open.bigmodel.cn/api/paas/v4/

# 通知
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=your_email@example.com
SMTP_PASS=your_email_password
DINGTALK_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=...
DINGTALK_SECRET=your_secret_here

# 采集器（注入 docker .env，gitignore）
MINISOC_API_KEY=                    # 采集器统一 Key
WAZUH_PASSWORD=                     # Wazuh API 密码
ROUTER_PASSWORD=                    # TP-Link 路由器密码
SCANNER_ID=                         # 攻击面扫描器 ID（admin 注册后下发）
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

---

## 开发与测试

### 代码规范

- **后端**：Python 3.13 + 类型注解，PEP 8；lint 用 ruff（CI 当前 advisory 不阻塞）
- **前端**：ESLint + Prettier + Stylelint；CI 当前 advisory 不阻塞（历史欠账）
- **提交**：Conventional Commits（项目实际不用 `(<scope>)` 前缀，常用 emoji）

### 运行测试

```bash
# 后端单元 + 集成测试（需 TEST_DATABASE_URL）
cd src/backend
PYTHONPATH=. ../../venv/bin/python -m pytest                          # 全部
PYTHONPATH=. ../../venv/bin/python -m pytest tests/unit               # 仅单元
PYTHONPATH=. ../../venv/bin/python -m pytest tests/integration        # 仅集成

# 前端单元测试
cd src/frontend
npm test

# 评测集（需 GLM key）
PYTHONPATH=src/backend ../../venv/bin/python scripts/eval_asset_query.py

# E2E（GitHub Actions，已禁用）
.github/workflows/e2e.yml
```

### CI / CD

| Workflow | 状态 | 说明 |
|---|---|---|
| [`.github/workflows/ci-backend.yml`](.github/workflows/ci-backend.yml) | ✅ | 后端 CI（lint + pytest） |
| [`.github/workflows/ci-frontend.yml`](.github/workflows/ci-frontend.yml) | ✅ | 前端 CI（lint + build） |
| [`.github/workflows/unit-tests.yml`](.github/workflows/unit-tests.yml) | ✅ | 单元测试汇总 |
| [`.github/workflows/e2e.yml`](.github/workflows/e2e.yml) | 🚧 禁用 | 旧 runner 下线，重启方法见文件头注释 |
| [`.github/workflows/deploy-prod.yml`](.github/workflows/deploy-prod.yml) | ✅ | CD：CI 全绿 → self-hosted runner → 自动部署 102 |

**发版**：直接 `git push origin master`，CI 全绿后自动部署（约 1.5 分钟）。
手动回滚 / 重部署：`.github/workflows/deploy-prod.yml` 的 `workflow_dispatch`，填 commit SHA。

### 关键规范

- **响应包装**：HTTP 恒 200，业务码在 `body.code`（前端 axios 拦截器看 body.code）
- **后端目录启动**：必须从 `src/backend/` 启动以加载 `.env`
- **路由 component**：后端菜单 `component` 字段为相对名（如 `reconciliation`），前端 ComponentLoader 解析为 `/asset/reconciliation/index`
- **菜单 path 单复数**：DB `component` 用单数（如 `/asset/reconciliation`），前端跳转 URL 用复数（如 `/assets/reconciliation`）—— 二者解耦
- **告警分级阈值**：全项目唯一权威为 `app/core/alert_levels.py`（13/10/7/4），禁止再写裸数字比较
- **数据库**：所有业务表 `soc_` 前缀（`alembic_version` 除外）
- **数据库**：统计表数量前必须 `import app.models`，否则漏 import 的模块不会注册到 `Base.metadata`

---

## 项目状态

### Phase 1：基础监控 ✅ 完成
- [x] 部署 Wazuh SIEM（21 agent，规则 504/506）
- [x] 配置 Loki 日志聚合（7 天保留）
- [x] 集成 Grafana 仪表板
- [x] 健康检查脚本（ops-health-check）
- [x] 采集器框架（collector-framework）+ 三件套采集器

### Phase 2：平台与 AI ✅ 完成
- [x] 后端 API 框架（FastAPI + async SQLAlchemy）
- [x] 前端控制台（Vue 3 + Element Plus + Pinia + Tailwind）
- [x] 用户 / 角色 / 认证 / 审计（RBAC + JWT + 验证码 + 黑名单 + refresh rotation）
- [x] 资产管理（CRUD + 端口 + 标签 + 同步 + 溯源）
- [x] 采集器架构集成（wazuh / tplink / scanner）
- [x] AI 能力（GLM 统一底座，9 个消费点）
- [x] W0 评测集（asset_query_eval.yaml，基线 98%）

### Phase 3：AI 增强 ✅ 完成
- [x] F1.1 风险评分（score_asset 4 维度 + history 快照 + 升降判定）
- [x] F1.2 安全态势摘要（dashboard / asset overview）
- [x] F1.3 资产对账（shadow / offline / mismatch + 扫描器接入）
- [x] F2.1 L1 自然语言资产查询 + L2 复合查询（4 模板）
- [x] F2.2 AI 安全报告（weekly / monthly / on_demand / incident_driven）
- [x] F2.3 知识库（knowledge）
- [x] F3.1 变更影响分析（关键词 → 资产定位 → 粗粒度关联 → GLM 报告）
- [x] F3.2 生命周期 / EOL（operator 可手动覆盖）
- [x] F3.3 合规基线（compliance_rules.yaml + AI 解读）
- [x] F4.1 AI 反馈闭环（ai_feedback）
- [x] F4.2 主动推送 5 场景（含扫描器离线 6）
- [x] X1 权限矩阵（admin / operator / viewer / auditor 端点级隔离）

### Phase 4：数据可靠性与可观测性 ✅ 完成
- [x] 告警治理（聚合 / 分级 / 治理配置）
- [x] 脆弱性管理（KEV + SCA + SCAP）
- [x] 后台任务可观测性（task_observability）
- [x] 源健康 / 同步死信 / 对账差异三层聚合（data-health）
- [x] CI/CD 全链路（push → CI → CD → 部署 → 自动回滚）
- [x] 采集器 CI/CD 覆盖（deploy_collectors.sh）
- [x] Alembic 迁移历史补齐（39 迁移，幂等）
- [x] §十一 Go/No-Go（4 大类：数据、AI 质量、安全权限、指标）

### Phase 5：规模化（待启动）
- [ ] 集群化部署
- [ ] 拓扑建模（F3.1 完整版）
- [ ] 部门隔离（soc_assets 需 schema 改造）
- [ ] 插件市场
- [ ] 多租户

---

## 路线图

### 已完成（2026-06 ~ 2026-08）

| 周 | 交付 |
|---|---|
| 06-02 | JWT 登录硬化 / 审计日志前端 / 字典管理 / 系统配置前端 |
| 06-07 | Python 3.13 升级 / 采集器架构 / 数据同步 / 表名前缀规范化 |
| 08-19 | CI/CD 全链路上线（self-hosted runner + 自动回滚） |
| 08-21 | F1.3 资产对账 + /api/v1/data-health + F2.2 AI 安全报告 + F4.2 推送 5 场景 |
| 08-22 | X1 权限矩阵 + F3.1 变更影响分析 + F2.1 L2 复合查询 + 告警分级统一 + W0 评测 + 降级演练 + alembic 迁移补齐 |
| 08-26 | 攻击面扫描采集器 Phase 1+2 全量落地（Nmap + 控制面/数据面分离 + 影子资产入稽核） |

### 下一步建议

1. **评分权重校准**（CLAUDE.md 已声明推迟，条件：端口覆盖>80% 或接入第二台 Wazuh agent）
2. **部门隔离**（soc_assets 需 schema 改造，独立工单）
3. **batch-score 定时化**（治本：评分自然积累，免手动触发）
4. **拓扑建模**（F3.1 完整版，P5）
5. **`/data-health` 补 scanner:* 键展示**（DB 已有 record，端点展示层小 PR）

---

## 文档索引

| 文档 | 路径 |
|---|---|
| **Claude Code 协作指南**（含全部历史决策，v2.24） | [CLAUDE.md](CLAUDE.md) |
| **CI/CD 方案**（v2.7） | [docs/development/cicd.md](docs/development/cicd.md) |
| 数据库快速参考 | [docs/development/database-quick-reference.md](docs/development/database-quick-reference.md) |
| 数据库切换到 testdb | [docs/development/database-switch-to-testdb.md](docs/development/database-switch-to-testdb.md) |
| 安全检查清单 | [docs/development/security-checklist.md](docs/development/security-checklist.md) |
| 资产页面诊断指南 | [docs/development/资产页面诊断指南.md](docs/development/资产页面诊断指南.md) |
| 代码知识库 | [docs/code-wiki.md](docs/code-wiki.md) |
| 变更日志 | [CHANGELOG.md](CHANGELOG.md) |
| 安全策略 | [SECURITY.md](SECURITY.md) |
| 环境变量样例 | [.env.example](.env.example) |
| Wazuh 集成手册 | [docs/wazuh-integration-manual.md](docs/wazuh-integration-manual.md) |
| Wazuh 中文配置 | [docs/wazuh配置.md](docs/wazuh配置.md) |
| 设计文档（45 份） | [docs/design/](docs/design/) |
| 安装指南 | [docs/installation/](docs/installation/) |
| API 文档 | [docs/api/](docs/api/) |
| 实施计划 | [docs/plans/](docs/plans/) |
| Runbook | [docs/runbook/](docs/runbook/) |
| 运维手册 | [docs/operations/](docs/operations/) |

### 关键设计文档

- 资产发现与攻击面扫描（final） — [docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md](docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md)
- 控制面原型（5 tab 交互） — [docs/design/2026-08-26-control-plane-prototype.html](docs/design/2026-08-26-control-plane-prototype.html)
- 部署架构图 — [docs/design/2026-08-26-deployment-architecture.svg](docs/design/2026-08-26-deployment-architecture.svg)
- 告警分级阈值统一 — [docs/design/2026-08-22-alert-level-threshold-unification-patch.md](docs/design/2026-08-22-alert-level-threshold-unification-patch.md)
- P4 验收报告 — [docs/design/2026-08-22-p4-acceptance-report.md](docs/design/2026-08-22-p4-acceptance-report.md)
- 数据可靠性全面梳理 — [docs/design/2026-08-16-数据可靠性全面梳理与完善方案.md](docs/design/2026-08-16-数据可靠性全面梳理与完善方案.md)
- 上网行为异常检测设计 — [docs/design/2026-08-03-browsing-anomaly-detection-design.md](docs/design/2026-08-03-browsing-anomaly-detection-design.md)
- 告警治理设计 — [docs/design/2026-08-09-alert-governance-design.md](docs/design/2026-08-09-alert-governance-design.md)
- 产品愿景与技术路线图 — [docs/design/product-vision-and-technical-roadmap.md](docs/design/product-vision-and-technical-roadmap.md)

---

## 贡献指南

欢迎贡献！请阅读 [CLAUDE.md](CLAUDE.md) 了解本项目的协作约定，提交前请：

1. Fork 仓库并创建特性分支（项目实际只使用 master，不存在 develop / main）
2. 遵循代码规范（前端 `npm run lint`，后端 ruff）
3. 补充必要的测试用例
4. 使用 Conventional Commits 提交信息（项目实际不用 `<scope>` 前缀）
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

<sub>📅 最后更新：2026-08-26 · 🏷️ 版本 v2.4（基于 P3+P4 全量交付）</sub>