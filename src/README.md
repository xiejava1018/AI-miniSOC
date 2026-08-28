# AI-miniSOC · src/

> `src/` 目录说明 —— 包含后端（FastAPI）、前端（Vue 3）和采集器（Docker）三个子项目。

## 目录

| 子目录 | 说明 | 启动命令 |
|---|---|---|
| [`backend/`](backend/) | FastAPI 后端（Python 3.13） | `cd backend && ../../venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload` |
| [`frontend/`](frontend/) | Vue 3 + Vite 前端（npm） | `cd frontend && npm install && npm run dev` |
| [`collectors/`](collectors/) | 容器化采集器（tplink / wazuh / scanner） | `cd collectors && docker compose up -d` |

## 前置要求

| 组件 | 版本 / 要求 |
|---|---|
| PostgreSQL | **16+**（生产实测 16.15） |
| Node.js | **18+**（前端开发） |
| npm | 9+（前端，**不用 pnpm**） |
| Python | **3.13**（本地开发，venv 已固定在仓库根） |
| Docker & Compose | 最新稳定版（采集器部署） |

## 快速开始

### 1. 克隆项目
```bash
git clone https://github.com/xiejava1018/AI-miniSOC.git
cd AI-miniSOC
```

### 2. 配置环境变量
```bash
cp .env.example .env
# 编辑 .env 填入真实配置（DB_HOST / GLM_API_KEY / WAZUH_* / LOKI_URL …）
```

### 3. 数据库准备
必须创建三个库，**绝不混用**：
```bash
psql -U postgres -c 'CREATE DATABASE "AI-miniSOC-db";'         # 生产（CI/CD 自动部署）
psql -U postgres -c 'CREATE DATABASE "AI-miniSOC-testdb";'      # 本地 dev
psql -U postgres -c 'CREATE DATABASE "AI-miniSOC-db_test";'     # pytest 专用
```

### 4. 启动后端
```bash
cd src/backend
# 必须从此目录启动以正确加载 .env（pydantic-settings 从 cwd 找）
../../venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# 健康检查：curl http://localhost:8000/api/v1/health
```

### 5. 启动前端
```bash
cd src/frontend
npm install
npm run dev       # 开发服务器: http://localhost:3006
# 生产构建（vue-tsc 必挂，用 npx vite build）：
npx vite build
```

### 6. 启动采集器
```bash
cd src/collectors
# .env 中需配置 MINISOC_API_KEY / WAZUH_PASSWORD / ROUTER_PASSWORD / SCANNER_ID
docker compose up -d
docker compose ps
```

## 访问入口

| 服务 | 地址 | 备注 |
|---|---|---|
| 前端（dev） | http://localhost:3006 | Vite 开发服务器 |
| 后端 API | http://localhost:8000 | FastAPI |
| API 文档 | http://localhost:8000/docs | OpenAPI 3 |
| Grafana | `GRAFANA_URL`（见 `.env`） | `.env` 中配置 |
| Wazuh | `WAZUH_API_URL` | wazuh-wui 用户 |
| OpenSearch | `OPENSEARCH_URL` | 见 `OPENSEARCH_PASSWORD` |
| Loki | `LOKI_URL` | 默认 7 天保留 |

## 项目结构

```
src/
├── backend/           # FastAPI 后端
│   ├── app/
│   │   ├── api/        # 43 个路由模块
│   │   ├── core/       # config / security / permissions / response_wrapper / alert_levels
│   │   ├── models/     # SQLAlchemy ORM（52 张表，统一 soc_ 前缀）
│   │   ├── schemas/    # Pydantic 数据契约
│   │   ├── services/   # 60+ 业务服务
│   │   ├── observability/  # Prometheus / OpenTelemetry
│   │   └── mcp/        # MCP（Model Context Protocol）
│   ├── alembic/        # 39 个迁移（head `u3v4w5x6y7z8`）
│   ├── tests/          # 单元 / 集成测试
│   └── main.py         # FastAPI 入口（lifespan 注册所有 scheduler）
├── frontend/          # Vue 3 + Vite 前端
│   ├── src/
│   │   ├── views/      # 11 顶级菜单 + 配置 + 占位
│   │   ├── components/ # 通用组件 + 业务组件
│   │   ├── api/        # API 客户端
│   │   ├── store/      # Pinia（持久化）
│   │   ├── router/     # 路由（后端驱动菜单）
│   │   └── hooks/      # useTable / useAuth / useSystem
│   └── vite.config.ts
└── collectors/        # 采集器（独立部署）
    ├── base/          # collector-framework 共享库
    ├── tplink/        # TP-Link 路由器资产采集器
    ├── wazuh/         # Wazuh SIEM 采集器
    ├── scanner/       # 攻击面扫描采集器（Nmap）
    └── docker-compose.yaml
```

## 技术栈

### 后端
- Python 3.13
- FastAPI 0.141（async）
- SQLAlchemy 2.0.36（async）
- PostgreSQL 16
- Alembic（39 个迁移，head `u3v4w5x6y7z8`）
- Pydantic v2 + pydantic-settings
- PyJWT + passlib[bcrypt]
- httpx + 0.28.1
- 智谱 GLM（统一大模型底座）

### 前端
- Vue 3.5.26
- TypeScript 5.6.3
- Vite 7.3.0
- Element Plus 2.13.0
- Pinia 3.0.4（持久化）
- Vue Router 4.6.4（后端驱动菜单）
- Tailwind CSS 4.1.18
- ECharts
- 基于 **art-design-pro-edge** 框架重构（已剥离多租户）

### 采集器
- Python 3.13（asyncio）
- httpx + collector-framework
- Nmap 7.95（scanner-collector）
- Docker（统一编排）

## 核心功能

### 已完成（v2.4，2026-08-26）

**资产管理**
- [x] 资产台账 CRUD + 标签 + 端口 + 数据源溯源
- [x] Wazuh 资产同步（全量 + Webhook 504/506）
- [x] TP-Link 路由器自动发现内网资产
- [x] 资产稽核（F1.3：shadow / offline / mismatch）
- [x] 数据健康（源健康 / 同步死信 / 对账差异）

**攻击面扫描**
- [x] 扫描采集器（控制面/数据面分离 + 拉模型）
- [x] Nmap -sV 端口服务识别
- [x] 扫描结果入 `soc_scan_findings` / 一键纳管 / 影子资产自动入稽核
- [x] 扫描器 watchdog + 离线通知（90s 判定）

**威胁检测**
- [x] 告警聚合 / 分级 / 治理配置
- [x] 告警摘要（每天 03:00 触发）
- [x] 脆弱性管理（KEV + SCA + SCAP）
- [x] 上网行为异常检测（browsing_detection）

**AI 能力**（GLM 统一底座）
- [x] 自然语言资产查询 L1（关键词筛选）
- [x] 自然语言资产查询 L2（4 模板受限执行）
- [x] 风险摘要 / 评分上升最快
- [x] AI 安全报告（weekly / monthly / on_demand / incident_driven）
- [x] 变更影响分析（关键词 → 资产 → 粗粒度关联 → GLM）
- [x] 对账 AI 解读 / 合规 AI 解读
- [x] AI Chat / AI Agent
- [x] W0 评测集（基线 98%，对抗样本 5/5 全拒）
- [x] 7 个 AI 消费点全部诚实降级演练通过

**用户与权限**
- [x] RBAC：admin / operator / viewer / auditor 端点级隔离
- [x] JWT + 刷新令牌 + 验证码 + 登录失败计数 + 自动锁定 + logout 黑名单 + refresh rotation
- [x] 按钮级权限（v-auth + require_button_permission）
- [x] 审计日志（AI 消费 / 对账 / EOL / 报告生成）

**通知与推送**
- [x] 多渠道通知（邮件 / 钉钉 / 微信）
- [x] 主动推送 5 场景 + 扫描器离线
- [x] 站内通知（WebSocket 实时）

### 进行中 / 计划中
- [ ] 评分权重校准（CLAUDE.md 已声明推迟，条件：端口覆盖>80% 或接入第二台 Wazuh agent）
- [ ] 部门隔离（soc_assets 需 schema 改造）
- [ ] batch-score 定时化
- [ ] 拓扑建模（F3.1 完整版）
- [ ] `/data-health` 补 scanner:* 键展示

## 文档

详细文档请查看 [`docs/`](../docs/) 目录：

- [架构设计](../docs/design/architecture.md)
- [产品愿景与技术路线图](../docs/design/product-vision-and-technical-roadmap.md)
- [CI/CD 方案（v2.7）](../docs/development/cicd.md)
- [P4 验收报告](../docs/design/2026-08-22-p4-acceptance-report.md)
- [资产发现与攻击面扫描（final）](../docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md)
- [Claude Code 协作指南](../CLAUDE.md)（v2.24，含全部历史决策）

## 许可证

[MIT](../LICENSE)