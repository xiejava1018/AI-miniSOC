# AI-miniSOC 项目开发指南

这个文件为 Claude Code (claude.ai/code) 提供 AI-miniSOC 项目开发时的上下文和指导。

## 项目概述

AI-miniSOC 是一个**AI驱动的微型安全运营中心**，集成了日志聚合、威胁检测、主机监控和AI分析能力。

当前开发环境位于 `/Users/xiejava/AIproject/AI-miniSOC`

## 技术栈

### 后端 (Backend)
| 技术 | 版本/说明 |
|------|----------|
| Python | 3.13 |
| FastAPI | Web框架 |
| SQLAlchemy | ORM |
| PostgreSQL | 数据库 |
| Pydantic | 数据校验 |
| PyJWT | JWT认证 |
| Pillow | 验证码图片生成 |
| python-dotenv | 环境变量管理 |

### 前端 (Frontend)
| 技术 | 版本/说明 |
|------|----------|
| Vue | 3.5.26 |
| TypeScript | ~5.6.3 |
| Vite | 7.3.0 |
| Element Plus | 2.13.0 |
| Vue Router | 4.6.4 |
| Pinia | 3.0.4 (持久化存储) |
| Tailwind CSS | 4.1.18 |
| Sass | 样式预处理器 |
| ECharts | 图表库 |
| axios | HTTP客户端 |

前端基于 **art-design-pro-edge** 框架重构，已剥离所有多租户代码。

## 项目结构

```
AI-miniSOC/
├── src/
│   ├── backend/              # FastAPI 后端
│   │   ├── app/
│   │   │   ├── api/          # API路由 (auth, users, roles, menus, departments, assets, data_sync, ...)
│   │   │   ├── core/         # 核心配置、认证、验证码、响应包装中间件
│   │   │   ├── models/       # SQLAlchemy 模型 (47张表)
│   │   │   ├── schemas/      # Pydantic Schema
│   │   │   ├── services/     # 业务逻辑层 (含 sync_handlers/)
│   │   │   └── database.py   # 数据库连接
│   │   ├── alembic/          # 数据库迁移
│   │   ├── tests/            # 测试
│   │   ├── main.py           # FastAPI 入口
│   │   └── .env              # 环境变量 (不上传Git)
│   │
│   ├── collectors/           # 外部采集器 (Docker部署)
│   │   ├── base/             # collector-framework 共享库
│   │   ├── tplink/           # TP-Link 路由器资产采集器
│   │   └── docker-compose.yaml
│   │
│   └── frontend/             # Vue3 前端 (art-design-pro-edge)
│       ├── src/
│       │   ├── api/          # API请求封装
│       │   ├── components/   # 业务组件 + 核心组件
│       │   ├── composables/  # 组合式函数
│       │   ├── config/       # 应用配置
│       │   ├── directives/   # 自定义指令 (v-auth)
│       │   ├── hooks/        # 通用Hooks (useTable, useAuth, ...)
│       │   ├── mock/         # Mock数据
│       │   ├── router/       # 路由配置 (后端驱动菜单)
│       │   ├── store/        # Pinia状态管理
│       │   ├── types/        # TypeScript类型定义
│       │   ├── utils/        # 工具函数
│       │   └── views/        # 页面视图
│       ├── package.json
│       └── vite.config.ts
│
├── docs/                     # 项目文档
│   ├── design/               # 设计文档
│   ├── development/          # 开发指南、日报
│   ├── installation/         # 安装指南
│   └── api/                  # API文档
│
├── configs/                  # 配置文件
├── scripts/                  # 工具脚本
├── skills/                   # Claude Code技能
└── CLAUDE.md                 # 本文件
```

## 后端API模块

所有API统一前缀 `/api/v1`，响应格式由中间件包装为 `{code, msg, data}`。
**注意**：HTTP 状态码恒为 200，业务成功 / 失败通过 `body.code` 区分（200=成功，401/403/4xx=业务错误）。

| 模块 | 路由文件 | 说明 |
|------|---------|------|
| 认证 | `app/api/auth.py` | 登录/登出/刷新Token/验证码/当前用户 |
| 用户管理 | `app/api/users.py` | 用户CRUD、重置密码、锁定/解锁 |
| 角色管理 | `app/api/roles.py` | 角色CRUD、菜单权限分配（含按钮权限） |
| 菜单管理 | `app/api/menus.py` | 菜单CRUD、菜单树（按角色过滤） |
| 部门管理 | `app/api/departments.py` | 部门CRUD |
| 审计日志 | `app/api/audit_logs.py` | 审计日志查询、CSV导出 |
| 资产管理 | `app/api/assets.py` | 资产CRUD |
| 资产端口 | `app/api/asset_ports.py` | 资产端口CRUD |
| 资产标签 | `app/api/asset_tags.py` | 资产标签CRUD |
| 资产事件关联 | `app/api/asset_incidents.py` | 资产↔事件多对多关联 |
| 字典管理 | `app/api/dicts.py` | 字典CRUD、字典项管理 |
| 系统配置 | `app/api/system_configs.py` | 系统配置CRUD |
| 事件管理 | `app/api/incidents.py` | 安全事件管理 |
| 告警管理 | `app/api/alerts.py` | 告警查询 |
| AI分析 | `app/api/ai.py` | AI日志分析 |
| 采集数据同步 | `app/api/data_sync.py` | 接收外部采集器推送的数据 |
| 同步任务 | `app/api/sync.py` | 同步任务状态查询 |
| 资产对账 | `app/api/asset_reconciliation.py` | P3/F1.3：触发对账、差异列表/摘要、AI 报告、差异处理（Wazuh 不可达返 503，不退化为无差异） |
| 数据健康 | `app/api/data_health.py` | P3/F1.3：源健康 + 同步死信 + 对账差异三层聚合（`soc_source_health`/`soc_sync_dead_letter` 的首个对外出口） |
| 安全报告 | `app/api/reports.py` | P3/F2.2：weekly/monthly/on_demand/incident_driven 四种触发；`data_coverage` JSONB NOT NULL 是硬门槛 |
| 主动推送 | `app/services/push_notification_service.py` | P3/F4.2：5 个场景全落地（源健康/评分突变/EOL/影子资产/报告生成完成）；`/api/v1/notifications/push-check` 手动触发，`/api/v1/notifications/push-rules` admin 配置 |
| 权限矩阵 | `app/core/permissions.py` | P3/X1：`require_role()` + `require_button_permission()`，P3 4 个写操作端点 + EOL 覆盖接权限；admin bypass、operator/viewer 实体测试通过 |
| 变更影响分析 | `app/services/impact_analysis.py` | P3/F3.1：`POST /api/v1/assets/impact-analysis`，自然语言变更描述 → 定位资产 + 粗粒度关联（同网段/共享标签/告警历史）→ GLM 报告（带模板降级）；admin/operator 可用 |
| L2 复合查询模板 | `app/services/query_templates.py` | P3/F2.1 L2：受限模板执行层（`configs/query_templates.yaml` 4 模板）。LLM 只选模板填参数，**不生成 SQL**；参数经类型/范围/枚举校验 + 维度二层白名单；统计类强制返回 coverage。入口仍为 `POST /api/v1/assets/ask`（自动路由 L1/L2） |
| Webhooks | `app/api/webhooks.py` | Wazuh Webhook接收 |
| 公共依赖 | `app/api/deps.py` | `get_current_user` / `require_active_user` / `require_admin` / `require_menu_permission` |

## 数据库表结构

| 表名 | 说明 |
|------|------|
| soc_users | 用户表（含nick_name, phone, avatar, gender, department_id） |
| soc_roles | 角色表 |
| soc_role_menus | 角色菜单关联表（含permissions JSONB按钮权限） |
| soc_menus | 菜单表（含permissions JSONB可用权限定义） |
| soc_departments | 部门表 |
| soc_assets | 资产表（含 `data_source`/`source_id`/`mac`/`wazuh_agent_id`、风险评分与 EOL 等字段） |
| soc_asset_ports | 资产端口表 |
| soc_asset_tags | 资产标签表 |
| soc_asset_sources | 资产数据源配置表 |
| soc_asset_change_logs | 资产变更日志表 |
| soc_incidents | 安全事件表 |
| soc_asset_incidents | 资产↔事件多对多关联表 |
| soc_audit_logs | 审计日志表 |
| soc_user_sessions | 用户会话表 |
| soc_password_history | 密码历史表 |
| soc_password_reset_tokens | 密码重置令牌表 |
| soc_system_config | 系统配置表 |
| soc_rate_limits | 限流表 |
| soc_ai_analyses | AI分析结果表 |
| soc_dicts | 字典表（含 dict_code 英文键） |
| soc_sync_tasks | 同步任务表 |
| soc_asset_change_logs | 资产变更日志表 |
| soc_notifications | 站内通知表 |
| soc_chat_sessions | AI对话会话表 |
| soc_chat_messages | AI对话消息表 |

> 实际共 **47 张表**（`import app.models; from app.models.base import Base; len(Base.metadata.tables)`）。
> 生产库 48 个（多出的是 `alembic_version`）。上表仅列核心表，P0–P3 陆续新增的
> 告警聚合、脆弱性、SCA、任务可观测性、源健康、同步死信、风险/EOL/合规/知识库/对账等表未全部展开。
> **注意**：统计前必须 `import app.models`，否则漏 import 的模块不会注册到 `Base.metadata`
> ——曾因此让 `alembic check` 误报要 DROP 8 张表（已于 `7600a1a` 修复）。
> 所有业务表统一使用 `soc_` 前缀（`alembic_version` 除外）。

## 前端核心特性

### 1. 后端驱动菜单
- 登录后从 `/api/v1/menus/tree` 获取菜单树
- `backendMenuToRoute()` 将后端菜单格式转换为前端 `AppRouteRecord`
- 后端菜单的 `component` 字段直接使用实际组件路径（如 `/system/user`）

### 2. 按钮级权限 (RBAC)
- 菜单表 `permissions` 字段定义可用按钮权限 `[{title, authMark}]`
- 角色菜单关联表 `permissions` 字段存储已授权的权限标识 `["add", "edit", "delete"]`
- 前端通过 `v-auth` 指令或 `useAuth()` Hook 控制按钮显示
- `hasAuth('add')` 检查当前路由下是否有新增权限

### 3. 路由别名
文件：`src/frontend/src/router/routesAlias.ts`

```typescript
export enum RoutesAlias {
  Layout = '/index/index'
  Login = '/auth/login'
  ForgetPassword = '/auth/forget-password'
  Exception403 = '/exception/403'
  Exception404 = '/exception/404'
  Exception500 = '/exception/500'
  Dashboard = '/dashboard/console'
  User = '/system/user'             // 账户管理
  UserCenter = '/system/user-center' // 个人中心
  Role = '/system/role'
  Menu = '/system/menu'
  Department = '/system/department'
  AuditLog = '/system/audit-log/index'
  Dict = '/system/dict'             // 字典管理
  SystemConfig = '/system/config'   // 系统配置
  Assets = '/asset/list/index'
  AssetDetail = '/asset/detail/index'
  Incidents = '/placeholder'        // 事件管理（占位）
  Alerts = '/placeholder'           // 告警管理（占位）
  Vulnerabilities = '/placeholder'  // 脆弱性管理（占位）
  Placeholder = '/placeholder'      // 功能开发中占位页
}
```

### 4. 响应适配
- 后端统一返回 `{code, msg, data}` 格式
- `useTable` Hook 的 `responseAdapter` 自动适配分页数据
- `defaultResponseAdapter` 支持 `records`/`data`/`list`/`items` 等多种字段名

### 5. 动态系统信息（System Info）

系统名称 / Logo / 版权 / 描述从 `soc_system_config` 表读取，不再硬编码。

- **后端公开接口**：`GET /api/v1/public/system-info`（无需鉴权，路由 `src/backend/app/api/public.py`）
  - 白名单字段：`system_name` / `system_logo` / `system_copyright` / `system_description`
  - 数据源：`soc_system_config` 中 `category='general'` 的 4 条记录
  - DB 缺失时回退硬编码默认值（`AI-miniSOC` 等）
- **前端 Pinia 存储**：`src/frontend/src/store/modules/system.ts`
  - state: `appName` / `logo` / `copyright` / `description` / `loaded`
  - 同样内置 FALLBACK 常量，DB 接口失败时静默回退
  - 配套 API 封装：`src/frontend/src/api/public.ts`
- **启动预拉取**：`src/main.ts` 的 `bootstrap()` 改为 `async`，**先 `await useSystemStore().fetchSystemInfo()` 再 mount**。保证首屏 `<title>`、登录页 Logo 旁文字、关于卡片都不会闪现旧名
- **页面 title 拼接**：`src/utils/router.ts` 的 `setPageTitle()` 从 `useSystemStore().appName` 读后缀
- **应用范围**：登录/忘记密码/关于项目卡片/侧边栏 Logo 旁文字/顶栏 Logo 旁文字/水印等 8 处 UI 全部从 `useSystemStore()` 取值
- **兜底**：`index.html` 的 `<title>` 和 `<meta description>` 改为 `AI-miniSOC`，避免 JS 加载前一片空白

## 核心组件

### 已部署的监控栈

#### Wazuh SIEM
- **位置**: 192.168.0.30:55000
- **功能**: 安全信息和事件管理
- **数据源**: 多个主机的日志
- **OpenSearch**: 192.168.0.40:9200（详见下方 OpenSearch 小节）

#### OpenSearch (Wazuh 索引后端)
- **地址**: https://192.168.0.40:9200
- **账号**: admin / 密码见 `.env` 的 `OPENSEARCH_PASSWORD`（示例：`xiejava*Happy99`）
- **集群**: wazuh-cluster，状态 green，单节点
- **用途**: 仅存 Wazuh 检测出的**结构化告警/脆弱性数据**，不存原始日志
- **索引规模**（2026-08 实测）：
  - `wazuh-alerts-4.x-*`：164 个，**103 万+ 告警文档**（按天分索引）
  - `wazuh-states-vulnerabilities-*`：14 个，10.1 万脆弱性状态
  - `wazuh-monitoring-*` / `wazuh-statistics-*`：Wazuh 自身监控/统计
  - 合计 238 个索引、约 136 万文档
- **告警字段**: `@timestamp` / `agent` / `rule` / `decoder` / `full_log` / `input` / `location` / `manager` 等
- **数据流原则**: 原始日志进 Loki，仅检测出的告警/事件进 OpenSearch，再被 AI-miniSOC 消费

#### Loki 日志系统
- **位置**: http://192.168.0.30:3100
- **配置**: /etc/loki/config.yaml
- **保留策略**: 7天
- **最大查询**: 500天 (12000小时)
- **存储**: /data/loki
- **实际数据**（2026-08 实测）:
  - 唯一采集源 `exporter=OTLP`，`service_name=LAG/unknown_service`，`host=192.168.0.30`
  - 内容为 **TP-Link TL-R479GP-AC 路由器上网行为日志**（syslog：访问网址 + 使用应用）
  - `ip` 标签约 54 个（内网 192.168.0.x + 公网 IP），24h 日志量约 20 万+ 条
  - 日志中域名已结构化提取可直接做行为分析（如 copilot.tencent.com / chatgpt.com / google.com 等）

#### Grafana 可视化
- **位置**: https://grafana.xiejava.dpdns.org
- **数据源**: Loki, OpenSearch, Prometheus
- **仪表板**: Wazuh威胁检测, 系统监控

#### 主机监控
- **工具**: ops-health-check (位于 ../host-manage/)
- **功能**: 系统健康检查、容器/服务监控、安全检查
- **输出格式**: Markdown + JSON

### 日志数据源

当前监控的IP范围：
- **内网**: 192.168.0.2-192.168.0.128
- **外网**: 多个公网IP (通过路由器日志)

日志标签:
- `host`: 主机名
- `ip`: IP地址
- `job`: 任务类型 (wazuh-alerts, wazuh-test)
- `exporter`: OTLP
- `service_name`: 服务名称 (LAG / unknown_service)

## 开发规范

### 代码规范
- **Python**: 遵循 PEP 8，使用类型注解
- **JavaScript/TypeScript**: 使用 ESLint + Prettier + Stylelint
- **Shell脚本**: 遵循 ShellCheck 规范，支持 bash 3.2+
- **文档**: Markdown格式，中文优先

### Git工作流
```bash
# 主分支（项目实际只使用 master，不存在 develop / main）
master             # 唯一分支，fast-forward 更新

# 实际不创建功能分支，所有工作在 master 上直接 commit
# （如需分支隔离，可临时建 worktree，例如 .claude/worktrees/frontend-refactor）
```

### 提交信息规范
```
<type>: <subject>

<optional body>
```
类型（项目实际使用频次排序）：
- `feat`: 新功能
- `fix`: 修复
- `docs`: 文档
- `refactor`: 重构
- `chore`: 构建/工具
- `style`: 格式
- `test`: 测试
- `perf`: 性能
- `ci`: CI

> **注**：项目历史**不**用 `(<scope>)` 前缀（如 `feat(auth):` 不出现），用 emoji 也常见（🐛 ✨ 📝 🔧）。保持简洁即可。

## API 端点

### REST API (FastAPI)
```bash
# 基础URL
http://localhost:8000/api/v1

# 登录
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 验证码
curl http://localhost:8000/api/v1/auth/captcha

# 菜单树
curl http://localhost:8000/api/v1/menus/tree \
  -H "Authorization: Bearer <TOKEN>"
```

### Loki API
```bash
# 基础URL
http://192.168.0.30:3100/loki/api/v1

# 查询日志
GET  /query_range
GET  /query

# 标签查询
GET  /label
GET  /label/<name>/values
```

### Wazuh API
```bash
# 基础URL
https://192.168.0.30:55000/api

# 认证
POST /security/user/authenticate

# 查询告警
GET /alerts?offset=0&limit=10
```

## 常用命令

### 启动开发服务器（本地 Mac，dev）
```bash
# 后端 (从 src/backend/ 目录启动以正确加载 .env)
cd src/backend
../../venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd src/frontend
npm run dev        # 开发服务器: http://localhost:3006
npm run build      # 生产构建（注意: vue-tsc 必挂，用 npx vite build）
```

### 生产部署（192.168.0.102）— CI/CD 自动化

**已全自动（2026-08-19 起，详见 `docs/development/cicd.md`）**：
```
push master → CI（Backend/Frontend/UnitTests 全绿）
            → CD（self-hosted runner aisoc-prod-deployer）
            → deploy/deploy.sh：fetch → reset → pip → vite build → restart → 健康检查
失败 → 全局 trap 自动回滚（git reset + rebuild + restart）
```

**服务器后端进程管理（systemd，替代旧 nohup）**：
```bash
# 在 192.168.0.102 上（sudoers 已配 NOPASSWD，可无人值守）
sudo systemctl status aisoc-backend      # 状态（免密）/ start|stop|restart
sudo -n systemctl restart aisoc-backend # 重启（deploy.sh 用这个，免密）
tail -f /var/log/aisoc/backend.log       # 应用日志
sudo -n journalctl -u aisoc-backend -n 50  # systemd 日志（免密）
```

**手动部署指定 commit（不经 GitHub Actions）**：
```bash
ssh xiejava@192.168.0.102
cd ~/AIproject/AI-miniSOC
bash deploy/deploy.sh <commit_sha> "说明"
# 任何步骤失败 → 自动回滚到部署前 commit
```

**Self-hosted Runner 管理**：
```bash
sudo systemctl status actions.runner.*   # runner 服务（装在 102）
sudo systemctl restart actions.runner.xiejava1018-AI-miniSOC.aisoc-prod-deployer.service
tail -f ~/actions-runner/_diag/Runner_*.log   # runner 诊断日志
```

⚠️ **注意**：
- `src/backend/start.sh` **已废弃**（保留仅应急），生产用 systemd
- 前端生产由 nginx:8080 服务 `dist/`（deploy.sh 自动重建）
- alembic 迁移**永不在 CI/CD 自动跑**，由 DBA 审阅后手动执行
- 服务器到 github 慢（~456 B/s）：fetch 已限 `--depth=50 + timeout 120`，新仓库 clone 建议从 Mac 中转

### 数据库操作
```bash
# 直接创建表（绕过alembic）
cd src/backend
../../venv/bin/python -c "from app.core.database import engine; from app.models.xxx import XXX; XXX.__table__.create(engine, checkfirst=True)"

# 查看所有表
../../venv/bin/python -c "from app.models.base import Base; print(sorted(Base.metadata.tables.keys()))"
```

### Loki查询
```bash
# 查询特定IP的日志
curl -G http://192.168.0.30:3100/loki/api/v1/query_range \
  --data-urlencode 'query={ip="192.168.0.2"}' \
  --data-urlencode 'start=1772932355000000000' \
  --data-urlencode 'end=1773018755000000000'

# 统计日志数量
curl ... | jq '.data.result[0].values | length'
```

### 健康检查
```bash
# 运行健康检查
cd /home/xiejava/AIproject/host-manage
bash skills/ops-health-check/scripts/health-check.sh

# 远程检查
ssh xiejava@192.168.0.30 'bash -s' < skills/ops-health-check/scripts/health-check.sh
```

## 当前已知问题

### 日志中断
- **问题**: 192.168.0.2日志在凌晨1:27后停止（TL-R479GP-AC路由器）
- **影响**: 无法查看该主机最新活动
- **待解决**: 排查路由器日志推送服务

### Loki限制
- 查询限制10000条/次
- 需要分页查询大量数据
- 时戳使用纳秒级

### Alembic 迁移历史 ~~不完整~~（✅ 已修复 2026-08-22，commit 9238f78）
- 新迁移 `ab9cd0e1f2a3` 补齐 7 张手工建表 + 7 个手工列（幂等，生产零操作）
- 修 `i3j4k5l6m7n8`（menu_id 改 JOIN）、`d1e2f3a4b5c6`（downgrade 补删表）、
  `c5962ab1f662`（downgrade 删 autogenerate 倒置产物）
- **已验证**：空库 upgrade head（27 步 48 表）→ downgrade base（零错误零残留）
  → 再 upgrade 干净；生产 head 未变无需执行
- `alembic check` 仍有索引命名约定类 diff（pre-existing 噪音，CI advisory 不阻塞）
- 空库重建验证命令：`DB_NAME=<新库> ../../venv/bin/python -m alembic -c alembic.ini upgrade head`
  （DB_NAME 环境变量会覆盖 .env，经 pydantic-settings 生效）

### Lint 历史欠账（2026-08-19）
- 前端 ESLint 2614 个错误（2590 可 --fix）、后端 ruff 数百条、vue-tsc 类型错
- CI 里 lint 均为 advisory（不阻塞），待逐步清零后恢复阻塞

### CI pytest 仍 advisory（2026-08-19）
- CI logs/artifacts 需 admin token 才能读，个别失败用例待拿到日志后修复，修复后移除 continue-on-error

### ENCRYPTION_KEY 不是合法 Fernet 密钥（pre-existing, 2026-06-02 发现）
- 启动 warning: `Fernet key must be 32 url-safe base64-encoded bytes.. Using temporary key.`
- 临时密钥每次重启换 → 旧加密数据（如有）解不开
- **不阻塞功能**，但生产部署前必须修（生成 32 字节 url-safe base64 写入 .env）

### tests/integration/test_user_workflow.py::test_user_lifecycle（pre-existing）
- 测试 `assert response.status_code == 201` 但中间件包成 HTTP 200 + `body.code=201`
- envelope 设计 vs 断言风格不匹配
- 跑测试时如要全绿，需把断言改成 `body["code"] == 201`

## 开发优先级

### Phase 1: 基础完善 (进行中)
- [x] 前端重构 (art-design-pro-edge)
- [x] 剥离多租户代码
- [x] 后端驱动菜单
- [x] 部门管理模块
- [x] 角色菜单按钮权限 (RBAC)
- [x] 用户字段完善 (nick_name, phone, avatar, gender, department)
- [x] 验证码支持
- [x] 统一响应包装中间件
- [x] 审计日志前端 (`c50513e` 2026-06-02 完成)
- [x] 字典管理 (前后端)
- [x] 系统配置前端
- [x] JWT 登录硬化 (登录失败计数 + 自动锁定 + logout 黑名单 + refresh rotation)
- [x] 独立测试库 (TEST_DATABASE_URL + test_engine) + 44 个 in-process 测试
- [x] 顶栏头像 onerror 兜底
- [x] 系统名称/logo/版权/描述全量动态化（public 接口 + Pinia 预拉取 + 8 处 UI 引用改造）
- [x] 站内通知系统 + WebSocket 实时推送
- [x] 采集器架构集成 (collector-framework + tplink-collector)
- [x] 资产数据同步 (data_sync API + sync_handlers)
- [x] Python 虚拟环境升级到 3.13
- [x] 表名统一 soc_ 前缀（全部业务表合规）
- [ ] 补全项目文档
- [x] **CI/CD 全链路上线**（2026-08-19）：push → CI 全绿 → self-hosted runner 自动部署 192.168.0.102，失败自动回滚，单次部署 ~1.5min，详见 `docs/development/cicd.md`
- [ ] 集成现有监控工具
- [ ] 事件管理 / 告警管理 / 脆弱性管理前端页面（仍占位）

### Phase 2: AI能力
- [ ] 实现日志AI分析
- [ ] 异常检测模型
- [ ] 智能告警聚合
- [ ] 自然语言查询接口

### Phase 3: 增强功能
- [ ] 告警通知 (邮件/钉钉/微信)
- [ ] 报告自动生成
- [ ] 威胁情报集成
- [ ] 自动化响应

## 相关资源

- **Wazuh文档**: https://documentation.wazuh.com/
- **Loki文档**: https://grafana.com/docs/loki/latest/
- **Grafana文档**: https://grafana.com/docs/grafana/latest/
- **Claude Code**: https://claude.ai/code
- **art-design-pro-edge**: https://gitee.com/chnmig/art-design-pro-edge

## 注意事项

1. **日志保留**: Loki仅保留7天，重要数据需备份
2. **时间戳**: Loki使用纳秒级Unix时间戳
3. **认证**: Wazuh使用JWT认证，需定期刷新
4. **性能**: 大量日志查询注意分页，避免超时
5. **安全**: 不要在代码中硬编码凭证
6. **环境变量**: `.env` 文件不上传Git，参考 `.env.example` 创建（**键名必须 1:1 对应 `app.core.config.Settings` 字段**，如 `SECRET_KEY` 不是 `JWT_SECRET_KEY`）
7. **启动目录**: 后端必须从 `src/backend/` 目录启动才能正确加载 `.env`
8. **CORS**: 开发环境需将前端地址加入 `BACKEND_CORS_ORIGINS`
9. **状态映射**: 后端用户状态使用字符串枚举 (`active`/`disabled`/`locked`)，前端使用数字 (1/2)
10. **验证码**: 内存存储（5分钟过期），生产环境建议替换为Redis
11. **响应包装**: HTTP 状态码恒为 200，业务成功/失败通过 `body.code` 区分。前端 axios 拦截器要看 `body.code`，不要看 `response.status`
12. **测试库**: `pytest` 走独立库 `AI-miniSOC-db_test`，跑测试前需 `CREATE DATABASE "AI-miniSOC-db_test";`
13. **JWT 测试**: 部分 E2E 用例 (`tests/test_auth_api.py`) 走 live uvicorn (http://localhost:8000)，需要先启动后端进程
14. **PINIA 持久化**: 登录态、用户信息、菜单树等都持久化到 localStorage，登出时显式 `userStore.logOut()` 清
15. **生产部署**: 不要在 192.168.0.102 手动 nohup/uvicorn，用 systemd（`systemctl restart aisoc-backend`）；常规发版直接 push master，CI/CD 自动部署
16. **慢网注意**: 102 服务器到 github ~456 B/s，git fetch 已限 depth+timeout；大文件（如 runner 包）从 Mac 中转

---

## 今日补充（2026-06-07 session 续记）

> 本节由 Claude 续写，记录 6/2 后到 6/7 期间本会话发现的项目状态变化。

### 关键变更
- **Python 虚拟环境**：从 3.9.6 升级到 3.13.2
- **采集器架构**：新增 `src/collectors/` 目录，含 collector-framework 共享库 + tplink-collector（Docker 部署）
- **数据同步**：新增 `POST /api/v1/data/sync` 端点 + `sync_handlers/` 服务层（支持资产 upsert + 变更日志）
- **数据表**：从 20 张 → 24 张，新增 `soc_asset_sources`、`soc_notifications`、`soc_chat_sessions`、`soc_chat_messages`
- **表名规范**：全部业务表统一 `soc_` 前缀（`asset_change_logs` → `soc_asset_change_logs`，`sync_tasks` → `soc_sync_tasks`）
- **Phase 1 进度约 95%**：通知系统、采集器架构、数据同步、Python 升级、表名规范化已完成

### 采集器工作原理
- TP-Link 采集器默认每 300 秒（5 分钟）采集一次路由器在线设备列表
- 采集后通过 `POST /api/v1/data/sync` 推送到 AI-miniSOC
- 同步处理器对比 source + source_id 执行 upsert（新建/更新/跳过），写入变更日志
- 支持 `--once` 单次执行、`--interval` 自定义间隔、`--test` 连通性验证

### 本次未做但建议尽快处理
1. `ENCRYPTION_KEY` 修成合法 Fernet 密钥（pre-existing 启动 warning，重启丢加密数据）
2. 修 `tests/integration/test_user_workflow.py` 的 envelope 断言
3. ~~数据库仍连 `AI-miniSOC-testdb`，生产环境应切到正式库~~（**已于 2026-08-18 完成**：服务器 `.env` 已切 `AI-miniSOC-db`，三层库分离见 cicd.md §1.2）

---

## 今日补充（2026-08-19 CI/CD 上线）

### 生产拓扑（本节为准）
- **生产服务器**: 192.168.0.102（xiejava-8g-host），后端 systemd `aisoc-backend`（port 8000），前端 nginx:8080 服务 dist
- **数据库**: **本机 PostgreSQL 16.15 `192.168.0.102:5432`**，生产库 `AI-miniSOC-db`（2026-08-23 从远端 111.228.57.2:25432 迁移过来，见「续八」）；本地 Mac dev 用 `AI-miniSOC-testdb`；pytest 专用 `AI-miniSOC-db_test`——三个库严格分离，**本地 .env 绝不指向生产**
- **CI/CD**: GitHub Actions；CI 跑 GitHub 托管 runner，CD 跑装在 102 的 self-hosted runner `aisoc-prod-deployer`（label `prod-deployer`）
- **部署脚本**: `deploy/deploy.sh`（fetch depth+timeout / pip / vite build / systemd restart / HTTP+DB 双探活 / 失败全局 trap 回滚）
- **sudoers**: `/etc/sudoers.d/aisoc-deployer`（10 条 NOPASSWD 最小权限，deploy 无人值守）
- **E2E workflow 已禁用**（旧 runner 下线）；重启方法见 e2e.yml 头注释
- **完整方案**: `docs/development/cicd.md`（v2.7，含 v2.0→v2.7 全部演进与实测记录）

### 关键操作速查
```bash
# 发版：直接 push master（CI 全绿后自动部署，~1.5min）
# 手动部署指定 commit:
ssh xiejava@192.168.0.102 'cd ~/AIproject/AI-miniSOC && bash deploy/deploy.sh <sha> "说明"'
# 查部署日志: ssh ... 'tail -30 /tmp/aisoc-deploy.log'
# 后端重启/日志: sudo -n systemctl restart aisoc-backend / tail -f /var/log/aisoc/backend.log
# Runner: sudo systemctl status actions.runner.*
```

### 遗留（不阻塞，按需修）
1. alembic 迁移历史缺 soc_menus 手工列 + 8 张 P4 表（check 一直 WARN，CI 用 create_all 绕过）
2. lint/pytest 仍 advisory（历史欠账：ESLint 2614 错、ruff 数百）
3. wazuh collector 的 config.yaml 明文密码在服务器端手工维护（未入库，待改 env/secret 注入）
4. 服务器上前端 `npm run dev`（nohup）仍在跑，可随时停（生产走 nginx:8080）

---

## 今日补充（2026-08-21 P3/F1.3 上线）

### 本次交付
- **F1.3 资产自动对账**：三类差异（shadow 影子资产 / offline 疑似下线 / mismatch 信息不一致）纯规则判定，AI 只做解读
- **`GET /api/v1/data-health`**：源健康（基础设施层）/ 同步死信（数据层）/ 对账差异（业务层）三层聚合
- 新增表 `soc_asset_reconciliations`；新增菜单「资产对账」`/assets/reconciliation`、「数据健康」`/assets/data-health`
- 迁移 `e4f5a6b7c8d9`（已在生产手动执行，当前 head）

### 实测要点（非推演）
- 生产真实对账：20 agent（manager `000` 已排除，Wazuh 共 21）/ 73 资产 / 9 项 offline，shadow 与 mismatch 均 0，无误报
- 状态机：首次 resolve 200、重复 409、非法状态 400，均生产实测
- AI 报告走通 GLM（`source=glm`），数据降级时首行强制声明可信度

### 踩过的坑（往后避开）
1. **菜单 `component` 与路由 `path` 不是一回事**：DB 的 `component` 存相对名（如 `reconciliation`），API 层转成 `/asset/reconciliation/index` 供 `ComponentLoader` 解析；而前端跳转要用路由 URL `/assets/reconciliation`（**复数**，父菜单 `/assets` + 子 path 拼接）。两者单复数不同，混用必 404
2. **排查菜单别按 `path` 查**：生产库 `soc_menus.path` 存的是中文名、`title` 大量为 NULL。按 `path='/asset/xxx'` 查会以为菜单没种进去（本次就误判一次），应按 `parent_id` 或 `component` 查
3. **`INSERT ... SELECT` 幂等写法会静默插 0 行**：父菜单解析不到时不报错，必须事后查表确认
4. **统计表数量前必须 `import app.models`**（见上方表结构注）

### 本地 push 应急
 Mac 到 GitHub 的 SSH 会间歇被切（现象：TCP 能连、发出本地版本串后即断，连 GitHub banner 都没收到，报 `Connection closed by ... port 22`）。
这**不是** key 问题（key 问题会报 `Permission denied`）。应急走 HTTPS（已存凭证 `credential.helper=store`）：
```bash
git push https://github.com/xiejava1018/AI-miniSOC.git master
```

---

## 今日补充（2026-08-21 P3/F2.2 上线）

### 本次交付
- **F2.2 AI 安全报告**。`soc_security_reports` 表 + `report_generator.py` 服务 + `/reports` 五个端点 + 前端报告列表/详情页。
- 迁移 `f2a3b4c5d6e7`（已在生产手跑，当前 head）；新增顶级菜单 `/reports` 与子菜单「报告列表」`/reports/list`。
- 事件驱动走 `POST /reports/check-incident-trigger` 同步端点（可被 cron 或前端按钮调），不引入消息队列（PRD 硬约束）。

### 实测（生产，2026-08-21）
- 真 AI 调用走通 GLM 3 次（weekly + 2× incident_driven）。
- summary 都开头声明「数据可信度降级，结果可能不全」；`data_coverage.gaps` 显式列「`loki:browsing_detection` 已 75 小时无成功记录」。
- incident_driven 阈值 3 触发：过去 24h critical+high 累计 48 条。
- prompt_version = `security-report-v1`。

### 踩过的坑（避开再犯）
1. **迁移里别写 Python 状态变量 + INSERT 后回读 SELECT**——`--sql` dry-run 不执行 INSERT，回读会报 `NoneType.scalar()`。改成纯 SQL 的 `INSERT … SELECT` + `NOT EXISTS`，与 F1.3 同款
2. **router `prefix` 与 endpoint 路径不要双重前缀**——`prefix="/reports"` + `endpoint="/reports/generate"` 会得到 `/api/v1/reports/reports/generate`。F1.3 是无 router 前缀、各 endpoint 写完整路径
3. **GLM prompt 里不要同时说「输出 JSON」和「用列表」**——LLM 会选 JSON 数组去装列表元素，导致 risk_highlights 变 `["a","b"]` 字符串。明确「每行以 - 开头，不要 JSON 数组、不要 Markdown 代码块」
4. **HTTP 路由级 bug service 层测试抓不到**——service 测过了不代表 endpoint 通。`check_incident-trigger` 因为调了 `svc._get_config()`（`_get_config` 是模块级不是方法），线上 500。本地端到端一定要用 `httpx.AsyncClient` 或起个 uvicorn test_client 跑过路由，不是只调 service 方法
5. **多级 ssh 转义会破坏 curl**——不要在 ssh 命令里嵌 `\"username\":\"admin\"`，改用 heredoc 或 base64 包

### F2.2 后的 P3 缺口
- ~~F1.3 资产对账~~ ✅
- ~~`/api/v1/data-health`~~ ✅
- ~~F2.2 AI 安全报告~~ ✅（本次）
- F4.2 推送场景 3/5（影子资产发现可接 F1.3、报告生成完成可接 F2.2）
- F2.1 L2 复合查询（P2/P3）
- F3.1 变更影响分析（P3）
- X1 权限矩阵补齐（横切）
- W0 准备阶段（前置）、§十一 Go/No-Go（上线门槛）

---

## 今日补充（2026-08-21 P3/F4.2 收尾）

### 本次交付
- **F4.2 五个推送场景全部落地**。原状：场景1 数据链路异常/2 评分突变/3 EOL 已实现；
  场景4 影子资产发现（依赖 F1.3）、场景5 报告生成完成（依赖 F2.2）本次补齐。
- 新增 `check_shadow_assets()` / `check_report_completion()`；
  `DEFAULT_PUSH_RULES` 加 `shadow_assets` / `report_completion` 默认配置（60s 缓存透明接管）。
- `run_all()` 返回新增两个键；`POST /api/v1/notifications/push-check` 端点已存在（admin only），不需新增。

### 实测（生产，2026-08-22）
- 插入 fixture 报告（PROD-CHECK-Weekly）→ push-check → admin 通知列表出现 `【报告就绪】PROD-CHECK-Weekly 7days`（type=push、link=/reports/list）。
- 第二次 push-check 同份报告被 24h dedup 拦下，stats.report_completion=0——dedup 工作正常。
- 场景5 类型白名单 default = weekly/monthly/incident_driven；on_demand 跳过（用户自己点的就不必再推）。

### 踩过的坑
1. **fixture 测完必须清理**，否则污染本地测试库 dedup 状态（本地 dedup 与生产是两套 DB，所以问题只发生在本地库）
2. **测 dedup 不能清 push 表**——把 dedup 依据也清了会假阳性
3. **`run_id` 是 NOT NULL**：fixture 影子资产必须给 run_id（PRD 加的字段，不是 NULL）
4. **多层 ssh escape 太脆**——内嵌 `\"` 在 ssh + bash heredoc 里会撞；改用 `cat > /tmp/xxx.py + scp + ssh` 三段，Python 内避免 emoji/中文括号（`·` 撞 Python3 ASCII）

### P3 剩余缺口
- F2.1 L2 复合查询（P2/P3）
- F3.1 变更影响分析（P3）
- X1 权限矩阵补齐（横切）
- W0 准备阶段（前置）、§十一 Go/No-Go（上线门槛）

---

## 今日补充（2026-08-22 P3/X1 权限矩阵）

### 本次交付
- **X1 权限矩阵**端点级落地。PRD X1 表里 admin/operator/viewer/auditor 的能力差异
  之前完全靠前端 v-auth 隐藏按钮——后端端点没区分，viewer 调 trigger 也能 200。
- 后端新增两个依赖：`require_role(*role_codes)`、`require_button_permission(menu_path, button)`；
  配 User.has_button_access() ORM 方法（admin bypass）。
- 4 个 P3 写操作端点接权限（端到端 HTTP 实测）：
  - `POST /assets/reconcile`                            → reconciliation, reconcile
  - `PUT  /assets/reconciliations/{id}/resolve`          → reconciliation, resolve
  - `POST /reports/generate`                            → list, generate
  - `POST /reports/check-incident-trigger`              → list, trigger
- EOL 覆盖（PUT/DELETE /assets/{id}/eol）改用 `require_role("admin","operator")`；
  原 _require_admin 太死（PRD §F3.2 + X1 都写明 operator 也能手动覆盖）。
- 报告生成落审计（AuditLogService.create_audit_log）；EOL/对账此前已落。
- 迁移 `g1h2i3j4k5l6`：种 operator/viewer/auditor + 4 菜单 × 3 角色 × perms JSONB 共 12 条授权。
  全 SQL 子查询写法，dry-run 干净 0 DROP。
- RoleCode 扩展：admin/operator/viewer/auditor（旧的 user/readonly 保留兼容）。

### 实测（生产 HTTP 路由级）
- admin:     /reconcile 200 / trigger 200
- operator:  /reconcile 200 / trigger 200
- viewer:    /reconcile 403 / trigger 403

### 踩过的坑（8 条，本轮反复重演）
1. **菜单 path 是相对名**（如 'reconciliation'），不是 '/asset/reconciliation'。一开始查全失败
2. **path 多匹配**：'list' 在 /assets 和 /reports 都有，has_button_access 必须 OR 全匹配，不是只查第一个
3. **响应包装中间件**：HTTPException(403) 被包成 status=200 + body.code=403，测试要读 body.code
4. **alembic 迁移别用 Python 状态变量 + INSERT 后回读**（--sql dry-run 炸）
5. **soc_role_menus 没 created_at 列**，INSERT 不要带
6. **soc_roles.name 也 unique**，种子不能与既有 '只读用户' 重名
7. **用户 fixture 测完要清理**，否则污染本地库 dedup/role 状态
8. **必须 HTTP 路由级实测**，service 层测过了路由未必通（F2.2 教训）

### X1 后续欠账（不在本轮范围）
- 全菜单权限补齐：本轮只种 4 个菜单；其余菜单仍是 admin 全通/其他人无权限
- 部门隔离：PRD 表写"operator 限本部门资产"，但 soc_assets 没有 department_id 关联，
  User.department_id 已有但需建 Asset↔Department 关联——独立工单
- 审计日志前端：当前只后端落，前端审计菜单能查但没专门页面

### P3 缺口最终状态
- F1.1 风险评分 ✅
- F1.2 安全态势摘要 ✅
- F1.3 资产对账 + 数据健康 ✅
- F2.1 L1 自然语言查询 ✅ / L2 复合查询 ❌
- F2.2 AI 安全报告 ✅
- F2.3 知识库 ✅
- F3.1 变更影响分析 ❌
- F3.2 生命周期/EOL ✅
- F3.3 合规基线 ✅
- F4.1 AI 反馈闭环 ✅
- F4.2 推送 5 场景 ✅
- X1 权限矩阵 部分 ✅（端点 + 角色 + 4 菜单授权）
- W0 准备阶段 ❌（前置，评测集部分已完成见下）
- §十一 Go/No-Go ❌（安全项已审计通过）

---

## 今日补充（2026-08-22 P3/F3.1 变更影响分析）

### 本次交付
- **F3.1 变更影响分析**（PRD P3 最后一个零代码的主功能）。自然语言描述计划变更，
  服务定位受影响资产 + 关联资产 + 历史告警，AI 输出可执行报告。
- **诚实降级**（PRD §F3.1 v1.2 明确要求）：拓扑建模不在本期范围，
  所以关联分析只做同网段 + 共享标签 + 告警历史三个粗粒度维度，
  前端三处（模板横幅 / 关联卡 tooltip / 模板文案）显式写"未包含拓扑信息"。
- 后端 `services/impact_analysis.py`：关键词提取（零 LLM 成本）→ 资产定位
  → 粗粒度关联 → OpenSearch 近 7 天告警分级 → 风险评分趋势 → GLM/模板报告。
- 前端 `views/asset/impact-analysis/index.vue`：左输入右报告，
  含目标资产明细卡（告警分级/评分趋势/关联台数）+ 关键词卡（可解释性）。
- 迁移 `h2i3j4k5l6m7`：菜单 #41 挂 /assets 下 sort=7，admin + operator 各授 view/analyze。

### 生产实测（真资产 + 真 GLM）
- admin 200 / operator 200 / viewer 403 / 未匹配资产 200+template
- 审计日志落库（3 条 resource_type=impact_analysis）
- 真实输出：`fnos-vm-ubuntu01/192.168.0.30`，近 7 天告警 medium 56 / low 146，
  同网段 15 台；degraded 真触发并正确报出 `loki:browsing_detection 过期 84.3h`

### 生产实测暴露并修复的 3 个真问题（commit d227d4f）
1. **GLM 把 recommendations 嵌成 JSON 对象 + 编造 2023 年日期**
   ——实测输出 `{'maintenance_window': {'start': '2023-04-01T00:00:00'}}`。
   prompt 未约束三字段必须纯文本 + `str(dict)` 直接吐 Python repr。
   修：prompt 加硬约束（禁嵌 JSON / 禁具体日期，只写相对表述）+ 新增
   `_flatten_to_text()` 把 dict/list 递归扁平为可读文本。**F2.2 同款坑的通用解**。
2. **target_count 从 1 膨胀到 7**（误匹配）——"升级 192.168.0.30 的 Wazuh Agent"
   把 Wazuh/Agent 当主机名 ilike，把精确 IP 信号淹了。
   修：信号强度分层 —— 精确 IP/CIDR 命中后跳过名称模糊匹配，
   且模糊匹配排除长度 < 4 的短词（k8s/vm）。
3. **degraded=True 但 summary 信息量 0**——只写"数据可信度降级"就结束。
   修：`_build_facts` 新增 `degrade_reasons[]` 传给 LLM，prompt 要求紧接说明原因；
   模板路径同步列出具体源名 + reason。

### 开发期踩坑（6 条）
1. `_serialize_asset` 定义成 @staticmethod 但 4 处按模块级函数调 → NameError
2. `sources`/`opensearch_ok_all` 只在 if targets 分支定义，未匹配分支 return 时炸
3. service 返回 `{"code":400}` 会被 API 再包一层变成 200 套 400；
   改 raise ValueError；实际 pydantic min_length/le 更早拦成 422
4. **soc_menus 没有 is_hidden 列，是 is_visible**（语义相反）——迁移首次直接失败
5. **soc_menus.component 存带前导斜杠的 `/asset/xxx/index`**，不是相对名；
   且有 title 列（旧数据大量 NULL，新增要补）
6. GLM 实测 20-60s，测试脚本 timeout=30 直接 TimeoutError，前端 API 封装设 180s

### P3 缺口最新状态
- F1.1 / F1.2 / F1.3 / F2.2 / F2.3 / F3.2 / F3.3 / F4.1 / F4.2 均 ✅
- **F3.1 ✅ 降级版**（拓扑建模属 P5）
- **F2.1 L1 ✅ / L2 ✅**
- X1 权限矩阵：**✅ 基本完成（2026-08-22）**——全菜单授权回填 + 合规/审计日志端点补齐 + 菜单树粒度 bug 修复；剩部门隔离（独立工单）
- W0 准备阶段：**✅ 基本完成**——50 条评测集（基线 98%）+ risk_history 回填（69/73）+ 权重校准显式推迟（触发条件已记录）
- §十一 Go/No-Go：**安全项 ✅**（LLM-SQL 路径审计）+ **降级演练 ✅**（7 个 AI 消费点全部诚实降级）；全量指标基线未做（需数据积累）

---

## 今日补充（2026-08-22 P3/F2.1 L2 复合查询 + 告警计数假阴性修复）

### 本次交付
- `configs/query_templates.yaml`（`templates_version: 1`，4 模板 + `unsupported_hint`）
- `src/backend/app/services/query_templates.py`：`load_templates()` 缓存、
  `template_catalog_for_prompt()`、`validate()`/`_coerce()`、`_DIMENSION_COLUMNS` 二层白名单、
  4 个 `_exec_*` 执行器、`execute()`
- `asset_query.py`：单次 LLM 调用完成 L1/L2 路由，`_run_l2()` + `_summarize_l2()`
- 前端：资产列表页 AI 查询区渲染 L2 三形态（统计 / 告警分级 / 资产列表）

### 四个模板
`port_open`（跨 soc_asset_ports）/ `offline_since`（时间窗）/
`asset_recent_alerts`（跨源 OpenSearch）/ `stats_group_by`（白名单维度分组）

新增模板 = 一条 YAML + 一个执行器函数，Prompt 主逻辑不动（模板清单动态渲染）。

### ❗ 本轮发现的生产假阴性 bug（已修）
交叉比对 L2 与 F3.1 对同一 IP 的告警数字时发现两边不一致，查下去是
**F3.1（已在生产运行）把 99 条 critical、635 条 high 报成了 0**：

| | total | critical | high |
|---|---|---|---|
| 旧实现（取文档分桶） | 204 | **0** | **0** |
| 服务端聚合（修复后） | 1637 | **99** | **635** |

根因：`get_alerts_by_ip(ip, limit=1000)` 取回文档再客户端分桶。该 IP 在
OpenSearch 里有 **47 万条 level-3 噪音告警**，按 @timestamp 倒序取「最近 1000 条」
几乎全是噪音，真正的 critical/high 全落在截断窗口之外。

附带两个问题：原实现算了 start/end 却从未传给查询（「近 7 天」名不副实）；
取值路径写成扁平 `al["rule_level"]`，而 `_normalize_alerts` 产出的是
嵌套 `al["rule"]["level"]`，恒取到 0。

**修法**：`AlertQueryService` 新增唯一权威实现（`size=0` 的 terms 聚合）：
- `get_level_buckets_by_ip(ip, days)` → 精确计数，返回 `exact=True`
- `get_high_severity_samples(ip, days, limit)` → 高危样例单独取文档

计数与样例分离：样例的 limit 截断不再污染计数准确性。
F3.1 `_alert_history` 同步改用该方法，两处口径现完全一致。

**教训**：在安全工具里把 99 条 critical 报成 0，比查询直接失败危险得多——
失败会被看见，假阴性会让人放心。**计数类需求一律用服务端聚合，
不要取 N 条文档再在客户端数**。

### 分级阈值口径
~~权威定义下沉到 AlertQueryService.LEVEL_*~~ → **已进一步下沉到
`app/core/alert_levels.py`（全项目唯一权威，commit 72c9a6a，2026-08-22）**：
13/10/7/4（critical/high/medium/low，level<4 视为噪音不计入）。

**ai_analysis 三处旧阈值（12/7 与 12/8）已统一**：生产量化依据——近 7 天
47,928 条告警中 level-10 有 4,921 条（10.3%），旧口径在「AI 分析」页标
"中风险"、在报告里计为 high。统一后 level 10-12 都标"高风险"。

**附带修复 asset_summary 双计 bug**：整数 level 被 isinstance 和 int()
各计一次，资产概览页高危数长期虚报约 2 倍；高危阈值同步 12→10。

**生产分数回归实测：零影响**——69 台重算仅 2 台 IOT 设备 -2 分，
breakdown 确认与 alerts 维度无关（它们的 P 级变化未被任何资产关联，
 属离线天数等其它维度正常波动）；主梯队分数全部不变。

新代码一律 `from app.core.alert_levels import LEVEL_*`，禁止再写裸数字比较；
`AlertQueryService.LEVEL_*` 保留 re-export 兼容。

### 开发期踩坑（本轮新增）
1. **`soc_assets` 无 `last_seen` 列**（用 `status_updated_at`，仅 7/73 非空）；
   **无 `department_id`**（用 `business_unit`，72/73 为 NULL）
2. **模糊字段名会直接造成 LLM 幻觉**：传给 GLM 的 facts 里叫 `total`（实为资产台数），
   摘要就输出了自相矛盾的「有1个告警，其中高优先级告警635个」。
   改名 `matched_asset_count` / `alert_counts.alert_total` + 硬约束后 3 次输出稳定。
   → **事实字段名必须自成量纲**
3. **同一问题不能因路由层不同而有不同诚实度**：「按操作系统统计」首问走 L2
   （带「49 台字段为空」覆盖率警告），作为追问却走 L1（无警告）。
   已把 L1 的 stats 意图**委托给 L2 `stats_group_by` 同一实现**。
4. 前端 `coverageRatio` 在 total=0 时返回 `null` 而非 100%——无数据就是无数据
5. 写 heredoc 测试脚本时，`cat > x.py` 如果没跟在 `cd ... &&` 同一行，
   文件会落在仓库根而不是预期目录

### 生产实测（d77eb8d，真 GLM + 真数据）
- 路由准确率 6/6：含「开着 SSH」自行推出 `port=22`、「没打补丁」诚实 `unsupported`
- `stats_group_by(os_name)` 披露 `coverage={total:73, counted:24, missing:49}`
- `offline_since(7)` 披露 `{offline_total:7, judged:3, unknown:4}`，4 台无时间戳不蒙猜
- F3.1 同步验证：生产现报 `critical 99 / high 635`（修前 0/0）
- 本轮 3 个 commit 无 alembic 迁移，无需人工执行

---

## 今日补充（2026-08-22 续：W0 评测集 + LLM-SQL 路径审计）

### W0 评测集（commit 88ffb2a）
- `configs/eval/asset_query_eval.yaml`（50 条）+ `scripts/eval_asset_query.py`
- **基线：49/50 = 98%**（glm-4-flash，intent-only 口径），对抗样本 5/5 全拒；
  分类最低 unsupported 85.7%；目标 ≥80%（PRD §九）
- 重跑：`PYTHONPATH=src/backend venv/bin/python scripts/eval_asset_query.py`
  （脚本内部会 chdir 到 src/backend——pydantic-settings 从 cwd 找 .env，
  不 chdir 会拿不到 GLM key 报 401，再被 ai_budget 熔断掩盖）
- 评测集抓到并修复 3 个真问题（详见 commit）：
  1. L1 stats 委托时非白名单维度被静默换成 asset_type（答非所问）
  2. GLM 编造 network_segment="数据库服务器所在网段"——新增
     `_strip_fabricated_text_params`：自由文本参数必须是提问原文子串
  3. 「没打补丁」被当 keywords 筛选（返回"没有找到"会被误读为没风险）
- 已知残留：q42（机器间连接）被路由到 keywords 筛选，返回 0 结果无危害，
  属 glm-4-flash 能力上限，记录不修

### Go/No-Go 安全项审计（无代码变更，纯审计）
**「系统中不存在任何 LLM 生成 SQL 的执行路径」——通过**：
- `app/` 全部 `.execute()` 均接 SQLAlchemy select() 构造体，
  零字符串拼接进 execute（f-string/format/% 全项目无命中）
- 原生 `text()` 仅 2 处且均为静态 SQL + 绑定参数（`SELECT now()`、
  DELETE 带绑定 cutoff）；另 3 处 import 未用
- 四个 LLM 消费文件（ai_analysis/asset_query/impact_analysis/report_generator）
  的查询均代码构造，LLM 只产文本摘要或选模板
- L2 路径：template_id 取自 YAML 注册表 + validate() 白名单/枚举/范围，
  执行器仅用 ORM；L1 参数全部流入 ORM filter（参数化）

---

### 降级演练记录（§十一，2026-08-22）
**方法**：本地 8001 端口起独立实例，`GLM_API_KEY=invalid`（env 覆盖 .env），
生产与本地主实例零影响；逐个调用 7 个 AI 消费点。

| AI 功能 | 降级行为 | 判定 |
|---|---|---|
| L1 资产查询 | 「AI 服务暂不可用，请稍后重试，或使用资产列表页的筛选器」+ 引导常规筛选 | ✅ |
| L2 复合查询 | 「AI 查询已达调用限额（今日配额或限流）」+ 引导筛选器 | ✅ | 
| 风险摘要刷新 | 回退规则引擎文案，显式标注「（规则引擎口径）」 | ✅ |
| 安全报告生成 | 「AI 解读未启用，以下为规则模板输出」+ 完整四章节数据 | ✅ |
| 变更影响分析 | 「AI 解读未启用，以下为基于事实拼出的模板分析（未包含拓扑信息）」 | ✅ |
| 合规 AI 解读 | generated=0 / fallback=10，全部回退规则文案，errors=0 | ✅ |
| 对账 AI 解读 | 模板报告 + 数据新鲜度降级警告（同步不新鲜显式声明） | ✅ |

**结论**：无一处静默编造或返回看似正常的错误数据；全部诚实声明降级。
§十一「演练过一次降级路径」✅。

**遗留小项（不阻塞）**：L2 查询降级文案说「已达调用限额」，但实际可能是
熔断（401 连续失败触发）——措辞略偏，行为本身诚实（都引导稍后重试）。

### risk_history 冷启动回填（W0，2026-08-22）
生产执行 `POST /assets/risk/batch-score`：73 台 → 69 评分 / 4 N/A
（agent 类资产全维度缺失，按 §4.5 显 N/A 非 0，行为正确）；历史快照落库，
趋势图与 delta_7d 环比自今日起积累。
**评分权重校准样本：显式推迟**——当前输入数据残缺（端口 17/73、告警仅
1 台有 agent、business_unit 98.6% 空），此时校准是拟合数据缺口而非风险本身；
触发重评条件：端口覆盖率 >80% 或接入第二台 Wazuh agent。

### 环境坑（本轮新增）
本地 venv `bin/python` 间歇性报「No such file or directory」（符号链完好，
重试即恢复，4 次/全天）——疑与 macOS Python.framework 有关，未定位，
遇此错直接重试即可，勿误判为 venv 损坏。

---

## 今日补充（2026-08-22 续二：X1 权限矩阵收尾）

### 交付（commit 6b943a6 + 5483945，迁移 i3j4k5l6m7n8）
- **菜单树粒度 bug（真安全漏洞）**：`menu_service.get_menu_tree` 原逻辑
  「父菜单在授权集合 → 全部子菜单放行」——给 viewer 授 /assets 根等于
  授了全部资产子菜单（对账/影响分析泄漏）。修正为子菜单须自身被授权，
  父菜单仅作为容器保留。存量 user/readonly 同获修复
- **合规两个写端点无保护**（run-check / interpret 登录即可触发，viewer
  也能烧 GLM token）→ `require_button_permission("compliance", ...)`
- **审计日志只许 admin**：auditor 有菜单无接口（摆设）→ admin+auditor
- **全菜单授权回填**：operator +9（含知识库编辑/验证、合规巡检/解读）、
  viewer +9 只读且**移除对账**（矩阵 ❌，此前误授）、auditor = viewer
  只读 + /system + audit-log + 对账只读；auto_extract 留 admin

### 生产实测（5483945）
- 端点矩阵 7/7：合规巡检/AI 解读/对账/报告/影响分析（admin+op 200，
  view+aud 403）、AI 查询四角色全 200、审计日志 admin+aud 200
- 菜单树 3/3：viewer 无对账/审计/影响分析、auditor 有审计日志、
  operator 无 /system
- 迁移 downgrade→upgrade 幂等验证过；临时测试用户已清理

### X1 剩余（显式推迟）
- **部门隔离**：`soc_assets` 无 `department_id` 列（用 `business_unit`，
  72/73 为 NULL），需 schema 改造 + 数据回填，独立工单；当前
  operator 对账处理无部门限制（仅限内网单人使用场景，风险可接受）

---

## 今日补充（2026-08-22 续三：todo#4 空库 alembic 跑通 → P3 收官）

### 交付（commit 9238f78）
- 新迁移 `ab9cd0e1f2a3`（插在断点前）：7 张手工表 + 7 个手工列幂等补齐；
  建表用 `Base.metadata` 局部 `CreateTable(if_not_exists)`，与 ORM 永远一致，
  避免第三份 schema 漂移
- 修三处旧迁移（详见 commit message）
- 验证：空库 upgrade head（27 步/48 表）→ downgrade base（零错误、
  仅剩 alembic_version）→ 再 upgrade 干净；**生产 head 未变，零操作**

### 排查中的认知修正（值得记）
1. 「upgrade 失败后表数量为 0」不是没跑——alembic 单事务模式，
   失败整体回滚，看版本号和表数都看不出跑到哪，要看最后一条
   Running upgrade + 错误
2. 空库建不出**业务种子行**（基础菜单/角色是运营数据不是 schema）：
   迁移里所有引用菜单行的 INSERT 必须 JOIN 菜单表而非硬编码 id，
   行不存在 → 静默 0 行跳过（g1 等旧迁移已是这个写法，i3j4k5l6m7n8
   之前违反了）
3. `DB_NAME=<库> alembic upgrade head` 可直接切库：pydantic-settings
   环境变量优先于 .env，`DATABASE_URL` property 动态拼

### P3 收官状态
§十一 Go/No-Go 四大类：
- 数据与迁移 ✅（空库 upgrade/downgrade + 对账源健康展示 + 报告完整性校验）
- AI 质量 ✅（breakdown 可见 / 溯源 / 合规无 LLM / EOL 来源标识 / 降级演练）
- 安全与权限 ✅（X1 矩阵落地 + 审计 + 白名单 + 无 LLM-SQL）
- 指标：查询准确率基线 ✅（98%）；其余指标需运行数据积累，待一个月后采集

---

## 今日补充（2026-08-22 续四：菜单重组 /ops 运维管理）

### 本次交付
- **新顶级菜单「运维管理」**(path=/ops, sort=8，icon=ri:tools-line，permissions=[])
- **移动 4 个子菜单**到 /ops 下：
  - 任务中心（原 /system sort=90 → /ops sort=1）
  - 数据健康（原 /assets sort=6 → /ops sort=2）
  - 变更影响分析（原 /assets sort=7 → /ops sort=3）
  - 知识库（原顶级 /knowledge sort=65 → /ops sort=4，path 同步规范化 '/knowledge'→'knowledge'）
- **资产对账 → 资产稽核**（仅 name/title，path 'reconciliation'/component/permissions 全保留）
- **/ops 不显式插 soc_role_menus** —— X1 修复的 parent_ids 容器逻辑自动从子菜单反推
- 迁移 `j1k2l3m4n5o6`，down_revision=i3j4k5l6m7n8，生产已手跑

### 实测
- 本地 4 角色菜单树：admin 4 子全在；operator 3 子（无 task-center）；viewer 2 子（仅 data-health + knowledge）；auditor 2 子 + /system 下 audit-log
- HTTP 端到端：admin 登录 + /menus/tree 返回 27 个子菜单 URL，/ops 下 4 个新 URL 正确
- downgrade→upgrade 循环幂等；/ops component 改 /index/index（与 /system /assets 容器一致）

### 踩过的坑
1. **/knowledge 的 path 要从 '/knowledge' 改成 'knowledge'**——顶级约定带前导斜杠、子菜单约定不带，原样保留会拼出 /ops//knowledge 双斜杠。downgrade WHERE 同时容错 `path IN ('knowledge', '/knowledge')` 处理中间态
2. **container 菜单的 component 不能用 /<name>/index**——本想配 /ops/index，/ops 下没有 index.vue 会 404。改成 /index/index（layout）才是其它 /system /assets /incidents /alerts 同款
3. **migration 文件写完别立刻迁移再修文件**——本地已升级后改文件，alembic_version 已记录新版本，重跑不再执行；只能 downgrade→upgrade 验证或手改 DB。教训：先把迁移代码 review 完再跑
4. **downgrade 顺序反于 upgrade**——FK 要求先复原子菜单 parent_id 再删父菜单，不能直接删 /ops
5. **空父菜单一开始没 WHERE parent_id IS NULL 也能匹配（path 唯一）**，反而更稳——重跑时 path 已规范化、parent_id 已更新但 migration 检测不到差异时仍能自我修复

### 设计决策记录
- **不移动前端 .vue 文件**（views/system/task-center/ 仍在原位）—— component loader 用字符串索引文件，URL 与文件路径解耦。最少改动面
- **/ops 本身 permissions=[]**（无按钮）—— 是容器不是页面，不应被 v-auth 误拦
- **资产对账 → 资产稽核 不改 button authMark**（reconcile/resolve/report）——这些是 IT 术语，稽核/对账都说得通；改 authMark 会牵动所有 require_button_permission 调用，风险大于收益

### 待办（不阻塞）
- 视觉确认：建议登录 admin 浏览器看侧边栏，验证 /ops 容器图标、子菜单展开/选中样式
- 旧 URL 重定向：原 /system/task-center 现在 404，如果有人存了书签需手动改。考虑加 router redirect？

---

## 今日补充（2026-08-22 续五：菜单顺序重排 + title/icon 补全）

### 本次交付（2 个迁移，一块提交）

**迁移 1：`k1l2m3n4o5p6_misc_menu_cleanup`**（修正 CLAUDE.md 过期注释时发现）
- /vulnerabilities title='脆弱性管理'
- /browsing title='上网行为'
- /incidents/list component '/incident/index' → '/incidents/index'（与文件目录对齐）
- 配套 git mv views/incident/ → views/incidents/

**迁移 2：`l1m2n3o4p5q6_top_menu_reorder_and_icons`**
- 顶级菜单重排按用户指定顺序：概览仪表板、资产管理、脆弱性管理、事件管理、告警管理、上网行为、安全报告、运维管理、系统管理（sort 1→9）
- /reports sort 50→7, /system sort 7→9（其它 7 个 sort 不变）
- 补中文 title：/dashboard='概览仪表板'、/assets='资产管理'、/system='系统管理'
- 补/修 icon：
  - /reports/list NULL→ri:file-list-2-line（唯一真无 icon）
  - /ops/impact-analysis '&#xe6a0;'→ri:flow-chart（HTML entity 不会渲染——是当初迁移手滑写错）

### 踩过的坑
1. **HTML entity 当 icon 不会渲染**——以前的人以为 iconify 支持 '&#xe6a0;'，实际不会。系统统一用 ri:* 格式（RemixIcon via iconify）。这类隐藏 bug 只能靠 menu 全量 icon 扫描发现
2. **CLAUDE.md 过期注释会误导**——「事件/告警/脆弱性管理前端页面（仍占位）」这条 P3 初期写的 checkbox 一直没更新，实际这些都已实现。光看文档会以为有 3 个占位，实际只有 1 个无 icon 的子菜单

### 最终菜单（生产实测）
```
[1] 概览仪表板      ri:bar-chart-box-line
[2] 资产管理        ri:computer-line
[3] 脆弱性管理      ri:shield-check-line
[4] 事件管理        ri:alert-line
[5] 告警管理        ri:notification-3-line
[6] 上网行为        ri:radar-line
[7] 安全报告        Document（非 iconify 格式但有 icon，待统一）
[8] 运维管理        ri:tools-line
[9] 系统管理        ri:settings-3-line
```

### 待办（不阻塞）
- /reports 顶级 icon 'Document' 是 Material 风格，与其它 8 个 ri:* 不一致——要不要换成 'ri:file-shield-2-line'（安全报告主题）？
- /system 子菜单 title=NULL（显示英文 path 'user' 'role' 'menu' 'department' 'dict'）—— 跟以前 /vulnerabilities 一样的 cleanup 工作

---

## 今日补充（2026-08-22 续六：资产稽核/安全报告 icon 修正 + 页面文案统一）

### 本次交付

**后端迁移 m1n2o3p4q5r6_fix_invalid_icons**
- /assets/reconciliation icon 'ri:git-compare-line' → 'ri:scales-3-line'
  — 根因：iconify-json/ri 库中**实际没有** git-compare-line（只有 fill/commit 等变体）
  — 之前的迁移是照名字面猜的，没验过存在性
- /reports icon 'Document' → 'ri:file-shield-2-line'
  — 根因：'Document' 是 Material Icons 字符串（Font class），不是 iconify 格式
  — iconify 静默失败不报错，肉眼看就是没图标

**前端文案统一 对账 → 稽核（7 个文件）**
- /asset/reconciliation/index.vue：13 处（标题、按钮、错误消息、注释）
- /asset/data-health/index.vue：第 3 层卡片 7 处（台账稽核/前往稽核/最近稽核 等）
- /api/asset.ts：JSDoc 注释 6 处
- /router/routesAlias.ts：注释 2 处
- **不改**：API 路径 /assets/reconcile*、reconciliation_type 字段（功能性）
- **不改**：对账管理后端文件 asset_reconciliation.py（PRD §F1.3 原文 "资产对账"）

### 踩过的坑（后续菜单改动需注意）
1. **icon 字符串不能拍脑袋**—— iconify-json/ri 库实际可用图标名需到
   https://icon-sets.iconify.design/ri/ 查询，常见拼写错误：git-compare-line
   （不存在）、git-commit-line（存在）、git-merge-line（存在）
2. **Material Icons 和 iconify 不能混用**—— 'Document' 'Settings' 'Shield'
   这些是 Material 的 Font class 名，iconify 不认。系统统一用 ri:* (RemixIcon)
3. **iconify 不存在的名字静默失败**——不报错也不显示，控制台无任何
   警告，只能靠全量扫描 menu.icon 库才能发现

### 验证
- 本地 menu tree 查 icon 都更新成功
- 生产 alembic upgrade head 跑过 m1n2o3p4q5r6
- 生产 HTTP /menus/tree 返回 /reconciliation icon=ri:scales-3-line、/reports icon=ri:file-shield-2-line
- 前端 vite build 1m6s 完成，dist 原子替换

### 后续菜单 icon 健全性
- 建议补一条 CI：检查 menu.icon 字符串必须在 iconify-json/ri/icons.json 中存在
- 未来加新菜单时直接查 https://icones.js.org/ 避免同类坑

---

## 今日补充（2026-08-22 续七：P4 WO-2 补丁落地）

### 本次交付（补上验收报告 §2 WO-2 有条件通过项）

**验证收读**：[docs/design/2026-08-22-p4-acceptance-report.md](design/2026-08-22-p4-acceptance-report.md)
认定 WO-2 wazuh/tplink 失败路径不达标，【/data-health】假绿。

**迁移 `n1o2p3q4r5r6_wo2_backfill_interval`**：
- 回填现有 tplink:collector / wazuh:agents 的 expected_interval_seconds=300
- 让 _source_status() 的 degraded 守卫对现有行也生效

**代码侧三文件加 source_health 记录**：
- `services/sync_handlers/asset_sync_handler.py`：handle() 包 try/except 源级异常
  记 record_failure；success 传 expected_interval_seconds；新增
  _SOURCE_HEALTH_INTERVALS 映射
- `services/wazuh_agent_sync.py`：sync_agents 与 sync_single_agent 的异常路径
  独立 session 记 record_failure（防被外层 rollback 灭）
- `services/asset_sync.py`：sync_from_wazuh / sync_single_asset / 
  sync_single_agent_webhook 都加成功+失败 record

**测试重写**：
- 删 test_source_health_coverage.py 合成 @track_task 探针
- 新增 test_wo2_real_failure_path.py 5 个真失败路径测试
- 跨 DB 问题：autouse fixture patch `app.core.database.SessionLocal` →
  TestingSessionLocal（生产不 patch，行为不变）

### 生产实测（2026-08-22 15:50）
部署后 GET /api/v1/data-health 输出：
- counter: healthy=2 degraded=1 down=0 unknown=0
- loki:browsing_detection: **degraded**（已 91.9 小时无成功记录，interval=300 起作用）
- tplink:collector: healthy
- wazuh:agents: healthy
- overall_status=**degraded**（对得上 v2.5 验收报告里 75h+ 过期的判断）

原来 v1.2 阶段 loki:browsing_detection 会被报为 healthy 的「假绿」现在正确标红。

### 踩过的坑（本轮）
1. **跨 DB 问题**：服务代码里 `_db.SessionLocal()` 绑 env 生产 DB
   （本地 dev = testdb），测试中走 TestingSessionLocal=testdb，两者不同。
   解决：autouse fixture patch _db.SessionLocal
2. **mock 真实 SQLAlchemy class 会 TypeError**：patch SyncTask 为 MagicMock
   后 db.add(mock) 会报 `state.class_.__name__`，因为 MagicMock 没有 __name__。
   解决：mock 高层方法（BaseSyncHandler.handle）不 mock ORM 类
3. **WazuhClient `str(e) = __name__`**：拆包装后某些错误 str() 返 '__name__'
   （是 SQLAlchemy/MagicMock 处理 class 时出现）。最终改用独立 session + 
   局部导入，不复用原 session 后稳定
4. **record_failure 写不进去**：独立 session 走 patch 后的 TestingSessionLocal；
   原 session 被外层 rollback 会灭掉本 session 的未 commit 修改。必须独立
5. **assertion 需独立 session 验**：测试函数内用 db (test session) 查会被
   事务隔离看不到。需用新 TestingSessionLocal 实例

### P4 复验状态
验收报告原结论「WO-2 有条件通过」现已补齐：
- wazuh/tplink 失败路径可见（record_failure 被调）
- expected_interval_seconds 已设（degraded 判定可用）
- /data-health 页面不再假绿（生产实测 loki 91.9h 过期正确标 degraded）
- 真实失败路径测试替代合成探针

§十一 Go/No-Go 4 大类补充：
- 数据与迁移 ✅：WO-2 补齐
- AI 质量 ✅（前轮）
- 安全与权限 ✅（前轮）
- 指标 ✅：查询准确率 98%（前轮）；源健康可观测性 ✅（本轮）

---

## 今日补充（2026-08-22：Top 10 高危资产「评分」口径澄清）

### 本次交付
澄清「资产概览」页三处「评分」的口径混淆——尤其用户反馈后才发现：
- **Top 10 高危资产** 卡片里那个「评分」字段（200+），**不是** F1.1 风险评分
  （`Asset.risk_score`，0–100，batch-score 落库快照）
- 而是 `AssetOverviewService._build_top_risky_assets()` 的 **D7 加权和**——
  关键资产 +100 + 高危端口×20 + 未关闭事件×30 + 开放端口≥5 +10 + 24h告警×1
- 同页「风险分布」环形图（F1.1）和「近 1 天上升最快」（F1.1）的「当前分」是另一回事

**本次只做澄清，不动后端公式**（按用户选择 C 方案）：
1. **卡片副标题** `(按风险评分排序)` → `(综合风险分，D7 加权和)`
2. **「评分」列 header 加 tooltip**（hover 显示 D7 加权项分解 + 一行注「与 F1.1 不同」）
   - 文件 `src/frontend/src/views/asset/overview/index.vue`
   - `D7_TOOLTIP` 常量、`QuestionFilled` 图标导入、`:deep(.d7-tooltip-content)`
     white-space:pre-line（tooltip 多行）
3. **不动** F1.1 / D7 公式本身；不动 Top 10 排序逻辑

### 为什么不动公式
- F1.1 加 criticality 直接加权 → 需权重校准样本，CLAUDE.md 已声明推迟
  （触发条件：端口覆盖率>80% 或接入第二台 Wazuh agent）
- D7 单独存在有合理性（实时、覆盖 N/A 资产）
- 用户在 P3 收尾后已认可「双轨」现状，本次只在 UI 层面对齐认知

### 未做但建议（独立工单）
- **A. Top 10 改用 F1.1 排序**：会让 Top 10 列表变短（N/A 资产多），需权衡
- **B. F1.1 加 criticality 直接加权**：真正治本，但需校准
- 「评分上升最快」rising 门槛修复（>=2 → >=1）+ 前端字段名 delta_7d → delta
  —— 用户前一轮也提到，本轮未做（用户只选了 C）

### 后续注意
- 加任何新菜单或卡片时，**遇到「评分」字样必须显式标注口径**（F1.1 / D7 / 其它）
- Element Plus tooltip 多行：必须 `#content` slot + `:deep()` CSS，默认 `:content` 不支持 `\n`

---

## 今日补充（2026-08-22：评分上升最快 rising 修复）

### 本次交付（v2.19 遗留项落地）
上一轮 v2.19 提到「评分上升最快」rising 数据为空，本轮根因 + 修复：

#### 三层根因
1. **数据**：从 2026-08-21 W0 冷启动回填后，**从未有过任何重打分**（无定时 batch-score），
   0/70 资产 `risk_score != W0 baseline`，770 条快照全在同一 1h14m 窗口内
2. **逻辑**：原 rising 硬卡 `>= 2 快照 / 1d 窗口`，叠加 W0 批所有 score 都相同 → 永远 Δ=0
3. **阈值**：原 `delta >= 10` 过高；score_asset 输入波动量级 ±3~8，阈值过滤掉所有真实异动

#### 修复（按用户选择「近期」方案）
| # | 文件 | 改动 |
|---|---|---|
| 1 | `asset_risk.py::overview()` | rising 语义改为「当前分 vs 上次评分」（取 history 第二新快照）；<br>删 `now - timedelta(days=1)` 1d 窗口；删 `>= 2` 快照门槛；<br>阈值 `>= 10` → `>= 5`；字段 `delta_7d` → `delta`；清掉 dead `now = _utcnow()` |
| 2 | `api/asset.ts` | `RiskOverview.rising[].delta_7d` → `delta`<br>（**不动** `AssetRiskDetail.score_breakdown.delta_7d`，那是不同语义） |
| 3 | `overview/index.vue` | 卡片标题 「近 1 天评分上升最快」 → **「近期评分上升最快」**；<br>副标题 `(Δ ≥ 10，需关注异动)` → **`(与上次评分对比 · Δ ≥ 5)`**；<br>列 header `1d 变化` → **`Δ vs 上次`**；<br>empty-text 同步 |

#### 业务语义决策：为什么不要「近 1 天」/「近 7 天」
- `score_asset` 4 维度中只有告警是「近 7 天累计」，其它都是当前快照或静态配置
- 「N 天上升最快」听上去像「昨天 vs 今天」的实时事件，**但分数不是高频事件指标**
- 「近期」+「与上次评分对比」自解释，不被「为什么不是 14d」类问题困住
- 「上次评分」语义对运维节奏诚实（batch-score 当前没有定时，间隔由运维决定）

#### 实测验证（本地 testdb）
batch-score 跑过一次，4 个资产 score 变化：
```
1c40c800 192.168.0.2.xiejava-8g-host     41 → 49  Δ=+8  ✓ 显示
b1d3ecee jumpserver                      50 → 57  Δ=+7  ✓ 显示
c1111167 xxxx                            38 → 31  Δ=-7  ✗ 下降不显示
cdfcee98 xxxx                            43 → 46  Δ=+3  ✗ < 阈值 5
```
curl `/risk/overview` 返回 rising count=2，名字/IP/delta 全对。

#### 踩坑（本次）
1. **「修复后立即能用」是误判**：单改 `>= 2 → >= 1` 不能产生数据，因为没有新快照
   - 真正治本：改「次新快照」语义 + 跑一次 batch-score
   - 教训：debug 数据类问题时，先查「最近一次写入距今多久」比查代码更高效
2. **score_asset 输入波动量级**：第一次跑批只产生 ±3~8 异动，原阈值 10 永远过滤
   - 教训：业务阈值要按公式输入的天然波动量级定，不是拍脑袋
3. **batch-score 没有定时**：CLAUDE.md 早期提过「W0 后等真实异动」，但实际系统没有触发器
   - 教训：手动触发的后台能力，配独立 dashboard 提醒「距上次评分 X 天」更友好

#### 后续建议（独立工单，不在本轮范围）
- 给 batch-score 加 6h 定时，让评分自然积累（治本）
- 「风险下降最快」卡：对称设计，让 Δ<0 也展示
- 「距上次评分 X 天」提醒卡：标记资产长期未重打分（数据陈旧）
- F1.1 评分权重校准：CLAUDE.md 已声明推迟到「端口覆盖率>80% 或接入第二台 Wazuh agent」

---

## 今日补充（2026-08-22：rising v2 修正「次新基线」语义不达生产预期）

### 本次交付（v2.20 → v2.21）

v2.20 升上生产后，rising 仍为空。补查发现：**生产环境两次 batch-score 之间 score 常常不变**，
用「次新快照」作基线永远 prev = current，Δ=0，错失了 W0 之后真正的异动。

#### 生产真实数据状态（之前踩坑里没有查出）
- 本地 testdb：770 条快照，分布 {11: 70}（W0 冷启动批量造，同资产同分）
- **生产实际只有 277 条快照，分布 {1: 1, 4: 69}**（手动 batch-score 零星产生）
- jumpserver 轨迹：42 (W0 20:58) → 50 (09:55) → 50 (11:22) → 50 (17:04)
  - 「次新快照」= 11:22 = 50 = current，Δ=0 → 错过 +8 的真异动
- 教训：**不能假设生产数据跟本地 testdb 一致**，CLAUDE.md 里“数表都一样”是伪命题

#### v2.21 修复
- 改用**「最早一条 history 快照」**作为基线 = 自首次评分以来的累计变化
- 文案同步：副标题「与上次评分」→「与首次评分」；列 header「Δ vs 上次」→「Δ vs 首次」
- 本地 testdb 验证：仍能显示 jumpserver +7、xiejava-8g-host +8
- **生产实测**：rising count=3
  - xiejava-8g-host (192.168.0.102) 30 → 44  Δ=+14
  - jumpserver (192.168.0.60)            42 → 50  Δ=+8
  - pve-ubuntu04-k3s-work1 (192.168.0.46) 32 → 37  Δ=+5

#### 踩过的坑（本轮）
1. **CLAUDE.md 里“数据都一样”是伪命题**——本地 testdb 有 W0 回填，生产没有。
   “if some session auto-applies .env from cwd”严重依赖调用路径，不能默认环境同质。
   以后调试“按期望该有数据却没”的场景，**必须先查生产 vs 本地数据差异**。
2. **“次新快照”语义不是万金油**——假设了“两点间会变”，生产上不成立。
   改“首次快照”后语义上变成“终身累计变化”，业务上也能接受（点进去详情页还能看趋势）。
3. **CI/CD 部署遇到慢网**——CLAUDE.md 提的“~456 B/s”**今轮亲身经历**，
   fetch origin 3 个策略都 timeout（~8min），回滚 trap 生效。
   应急：Mac `git bundle + scp`，服务器 `git fetch /tmp/xxx.bundle + reset` 手动重跑 deploy 剩余步骤。
   建议未来加一键 deploy 脚本：`git bundle-create-and-deploy.sh`。
4. **本次在 Mac 本地也误判了生产状态**——一开始说“0/70 资产 prev != current”，
   那是在本地 testdb 上查的；生产其实是 4 条快照/资产 + 1 个新写入，70 资产里
   真正变化的只有 jumpserver（其它都是数据残缺、公式结果稳定的资产）。

#### 后续建议（独立工单，不在本轮范围）
- ~~6h 定时 batch-score~~ 仍然是治本推荐（上升最快卡会随自然异动自动出数据）
- **加「距首次评分 N 天」卡**：标记资产历史跨度，方便判断「累计变化可信度」
  （只有 1 条快照的资产跳过）
- **bundle-deploy 脚本**：将 git bundle + scp + server-side reset 打包成一键，
  应对慢网跳点场景
- **环境同质性测试**：在 CI 里加一步「检查生产 vs 本地 sample 数据是否同质」，
  发现不一致立即告警（避免后续开发中重复踩这个坑）

---

## 今日补充（2026-08-23：采集器 unhealthy / 僵尸进程 → CI/CD 缺口）

### 起因与结论
巡检报告 192.168.0.102 两个问题（233 僵尸进程 + tplink 容器 unhealthy），怀疑
CI/CD 导致。**实测结论：与 CI/CD 完全无关**，是采集器代码缺陷，从容器第一天
（2026-08-08）就存在。排除证据：
- `grep -ci docker /tmp/aisoc-deploy.log` = **0**（deploy.sh 只碰 git/pip/vite/systemd）
- 容器 `RestartCount=0`、`Created=2026-08-08`，两周内几十次部署一次没动过
- `FailingStreak=20531` × 60s ≈ 14.25 天 ≈ 容器全生命周期 → 从第一次检查就在失败

### 真正的根因（两个问题同源）
**`tplink_collector/__main__.py` 的 `--test` 分支连开 3 个 `asyncio.run`**。
`MiniSOCClient.__init__` 里就构造 `httpx.AsyncClient`，连接池绑定到**首次使用**
的那个循环；第 3 个循环里 `aclose()` 去关第 2 个（已关闭）循环上的 transport →
`RuntimeError: Event loop is closed`。

关键认知：**健康检查日志显示路由器登录和后端 `/health` 都返回 200** ——
是收尾代码把成功的检查判成了失败，采集主循环一直正常（每 5 分钟同步 24-25 条）。
`/data-health` 把 tplink 报 healthy 是**对的**，docker 那个 unhealthy 才是虚警。

对照组说明一切：`wazuh/src/wazuh_collector/__main__.py` 把三步放进**一个**协程、
只 `asyncio.run` 一次 → 始终 healthy。同机、同框架、同天构建，唯一差别是这个写法。

僵尸进程：233 个**全部** PPID = 容器 PID 1。HEALTHCHECK 的 exec 子进程在容器 PID
命名空间里被 reparent 到 PID 1，而 PID 1 是普通 python 进程、从不 `wait()`。

### 交付（commit baad179 + 0b3c615）
- `__main__.py` 三个分支各收敛为**单次 asyncio.run**，收尾同循环内做；
  signal 改 `loop.add_signal_handler`
- `TPLinkCollector` 补 `close()`（BaseCollector 没这方法，路由器侧 client
  从来没人关过；`test_tplink.py` 调它其实会 AttributeError）
- compose 两服务加 `init: true`（tini 收尸），tplink HEALTHCHECK
  `timeout 5s→15s` + `start-period=15s`
- **`deploy/deploy_collectors.sh`** + deploy-prod.yml step 5：补上
  `src/collectors/` 完全在 CI/CD 之外的缺口（路径过滤触发、健康门禁、
  僵尸数核查、不自动回滚）

### 踩过的坑（本轮新增）
1. **本地 Mac 复现不出这个 bug**。httpx/httpcore/anyio 版本与容器**完全相同**
   （0.28.1 / 1.0.9 / 4.14.2），差异只在 Python 3.13.2 vs 3.12.13。
   一开始误判为「依赖版本差异」，实际是 Python 版本的 asyncio 行为差异。
   → **这类运行时行为 bug 必须在目标运行时里验**，本地跑通不代表线上跑通
   （与 F2.2「service 测过了路由未必通」同一类教训）
2. **第一次复现脚本用 HTTP/1.0 stub 服务器，连接不 keep-alive → 池里没有活
   transport → `aclose()` 无事可做，复现失败**。必须 `protocol_version="HTTP/1.1"`
   + Content-Length，或者直接打真后端（uvicorn keep-alive）
3. **验证修复不要直接改运行中容器的 site-packages**。用
   `docker cp` 到 `/tmp/patch` + `docker exec -e PYTHONPATH=/tmp/patch` shadow
   掉镜像里的旧包，既验证真代码又不污染运行中的容器
4. **僵尸进程别按「会耗尽 PID 表」定优先级**：`pid_max=4194304`，233 个差
   4 个数量级。修它的理由是它是 bug 的可见症状，不是资源风险
5. **`docker restart` 治不了本**：能清掉僵尸，但 healthcheck 继续失败 →
   原速重新堆积

### 顺手纠正 CLAUDE.md 两处过期记载
1. ~~「wazuh collector 的 config.yaml 明文密码在服务器端手工维护（未入库）」~~
   —— **已过期**。`src/collectors/wazuh/config.yaml` 是**入库**的，且内容全是
   `${WAZUH_PASSWORD}` 这类占位符，无明文密码；真凭证在 gitignore 的
   `src/collectors/.env`。服务器 `git status src/collectors/` 干净（无漂移）
2. 采集器**镜像**才是真正的手工维护面（本轮已纳入 CD）

### 追加：重建容器引爆了 wazuh 的隐形故障（同一天，commit 1810cd4）
`deploy_collectors.sh` 的健康门禁**第一次运行就抓到一个真问题**：tplink 变
healthy 的同时，wazuh-collector 起来即 `401 Unauthorized` 重启循环。

**凭证本身是好的**——拿 `.env` 里的值直连 Wazuh API 手工验证返回 HTTP 200，
且与 `src/backend/.env` 的 WAZUH_* 三项 md5 完全一致。

根因两层：
1. **`yaml.safe_load` 不展开 `${VAR}`**。仓库的 config.yaml 故意写
   `user: ${WAZUH_USER:-wazuh}` / `password: ${WAZUH_PASSWORD}`（不入库明文），
   而 `WazuhCollector.__init__` 只做 `wazuh_cfg.get("user", ...)` →
   把字面量字符串 `"${WAZUH_USER:-wazuh}"` 拿去认证 → 401
2. 那行的 fallback `config.extra.get("WAZUH_USER")` 是**无效代码**——
   `extra` 就是解析后的 YAML dict，根本没有顶层 `WAZUH_USER` 键。
   所以环境变量从头到尾没被读过一次

**为什么两周没暴露**：容器 2026-08-08 启动时读的是当时带真值的 config.yaml，
凭证已在内存里；后来某次部署的 `git reset --hard` 把该文件换成占位符版本，
进程没重启就一直正常。**一个「只要重启就挂」的地雷**——和 tplink 那个
「只要跑 healthcheck 就报错」一样，都是靠「从不重建容器」掩盖着的。
→ **这正是「不在 CI/CD 里」的真实代价：不是改了不生效，而是攒了一堆
只在下次重启时才一起爆的雷。**

修法：新增 `collector_framework.config.resolve()`——env 优先 → YAML → default，
并**识别未展开的 `${VAR}` / `${VAR:-default}` 占位符，绝不当值用**；
占位符且无 default（如 password）→ **启动期抛 ValueError**。
宁可启动失败，也不拿 `${}` 去发请求：一个启动期异常比日志里一万条 401 好查。

### 本轮最终实测（生产，2026-08-23 01:44）
| 指标 | 修复前 | 修复后 |
|---|---|---|
| 宿主机僵尸进程 | 233 | **0** |
| tplink health | unhealthy（streak 20531） | **healthy**（streak 0） |
| tplink `--test` 退出码 | 1 + traceback | **0**（路由器 OK / AI-miniSOC OK） |
| wazuh health | healthy（但重启即挂） | **healthy**（且重启后仍 healthy） |
| `init` / RestartCount | 无 init | `init=true` / restarts=0 |

### 又踩的坑（本轮追加）
1. **`PYTHONPATH` shadow 对 PEP 660 editable 安装无效**。wazuh 的
   `wazuh_collector` 装在 `/app/src`（不是 site-packages），且 editable 安装注册的是
   **meta-path finder**，它排在 `sys.path` 之前 → `PYTHONPATH=/patch` 被完全绕过
   （同样手法在 tplink 上是有效的，两个包安装方式不同）。
   验证补丁前先 `python -c "import x; print(x.__file__)"` 确认真实路径，
   再按该路径覆盖挂载
2. **`"\$"` 在 Python 里是反斜杠+美元**，`startswith("\$")` 恒 False，
   把「是不是占位符」判反了（还伴随 SyntaxWarning: invalid escape sequence）。
   用 `chr(36)` 或 `"$"` 才对——一个转义把整条结论带偏了
3. **同一个「验证脚本」在 ssh 里套多层引号极易失真**，本轮又中一次；
   多层嵌套时优先 `docker run --rm` 一次性容器 + 覆盖挂载，别改运行中的容器

### 顺带发现（未修，需决策）
**`sync_client` 把 `body.code=400` 当成同步成功**。wazuh 采集日志实录：
```
同步成功: {'code': 400, 'msg': '不支持的数据类型: baseline，当前支持: asset'}
```
即 CLAUDE.md 注意事项 #11 那个 envelope 陷阱（HTTP 恒 200、业务状态在
`body.code`）在采集器侧**没有遵守**——只看 HTTP 200 就记 success，
于是 vulnerability / baseline 两类数据其实一条都没进库，却一直报「同步成功」，
`soc_source_health` 也跟着记 success。**这是假绿，与「99 条 critical 报成 0」
同类**（失败会被看见，假成功不会）。
未直接修的原因：改成如实报失败会让 `wazuh:baseline`/`vulnerability` 立刻
record_failure → `/data-health` 转 degraded。这是**正确**的，但会改变面板颜色，
应由人决定是先补后端 `data/sync` 的类型支持、还是先让面板诚实变红。

### 待办（不阻塞）
- ~~等下次 CD 跑 `deploy_collectors.sh` 生效~~ ✅ 已于 2026-08-23 01:44 生效并实测（见上表）
- `run_daemon.py` 里 `subprocess.Popen` 那套守护逻辑与 docker
  `restart: unless-stopped` 功能重叠，线上未使用，建议后续评估是否删除
- **`sync_client` 不看 `body.code`**（见上「顺带发现」）：要么补后端
  `data/sync` 对 vulnerability/baseline 的支持，要么让采集器如实报失败
  并接受 `/data-health` 转 degraded。二者都行，但不能继续假绿
- 采集器凭证目前 backend/.env 与 collectors/.env 各存一份（值相同），
  建议后续收敛为单一来源，避免只改一处

---

## 今日补充（2026-08-23 续八：生产库从远端迁到 102 本机）

### 变更
生产 DB 由 **远端 `111.228.57.2:25432`** 切到 **102 本机 `192.168.0.102:5432`**（PostgreSQL 16.15），
库名/账号不变（`AI-miniSOC-db` / `aisoc`）。改的只有 `src/backend/.env` 的 `DB_HOST`/`DB_PORT`
（systemd `EnvironmentFile` 就是这份 .env，改完 restart 即生效）。

### 前置事实（勘察结论，非推演）
- 102 上早已跑着 PostgreSQL 16.15，`0.0.0.0:5432`；角色 `aisoc` 已存在且密码一致
- 本机 `AI-miniSOC-db` 已存在但**空库**（0 表）→ 可直接 restore，无需建库（`aisoc` 无 createdb/superuser，
  `sudo -u postgres` 也要密码，真要建库得先解决权限）
- 源库 52 MB / 49 表 / head `n1o2p3q4r5s6`；扩展只有 plpgsql（无需额外权限）

### 迁移过程
1. 停写：`systemctl stop aisoc-backend` + `docker stop` 两个 collector → 源库连接数 0
2. `pg_dump -Fc --no-owner --no-privileges -Z6`（88s，7.3 MB）
3. `pg_restore --exit-on-error -j2`（12s）
4. **逐表精确 count 比对**（不是 `n_live_tup` 估算，用 `query_to_xml` 动态 count）：49/49 表全等
5. 切 .env → restart → 探活 → 恢复 collector

### 实测核验
| 项 | 结果 |
|---|---|
| 表数 / 行数 | 49 / 49 全等（`diff` 零差异） |
| 序列 last_value | 13 个逐一与源库一致（含 NULL 的那几个） |
| 索引 / 外键 | 122 / 39，两边一致 |
| alembic head | `n1o2p3q4r5s6`（新库 `alembic current` 确认 head） |
| 业务探活 | 登录 200、`/menus/tree` 9 顶级、`/assets` total=74、`/data-health` 200 |
| 写入落点 | 新库 sync_tasks 40334 且 max(created_at) 持续增长；**旧库冻结在 10:15:58** |
| collector | wazuh / tplink 均 healthy，`POST /data/sync` 200 |

### 注意点
1. **`.env` 在 `src/backend/.gitignore` 第 1 行** → CI/CD 的 `git reset --hard` 不会把 DB_HOST 打回去；
   `deploy.sh` 的 DB 探活也是从 .env 动态读 `DB_HOST`，无硬编码 → **后续发版无需额外处理**
2. **目标库多出 2 个 view 属正常**：`pg_stat_statements` / `pg_stat_statements_info`（owner=postgres），
   是本机实例的扩展视图，不是应用对象。核验时按 `relkind in ('r','p')` 判空才不会误报
3. **序列 `last_value` 为 NULL 的 9 个表不是迁移丢了**——源库本身就是 NULL（那些表不走 serial）。
   判断「序列有没有丢」必须两边对照，不能只看目标库有没有值
4. `/health` 仍报 `degraded`（`browsing_detector` 自 08-18 未跑）——**迁移前就存在**，
   与本次无关（即 CLAUDE.md 里 loki:browsing_detection 过期那条）
5. **DB 现在监听 `0.0.0.0:5432`**，LAN 内可直连（迁移中就看到 192.168.0.8 的 DBeaver 连进来）。
   内网单人场景可接受，但比原先「远端库 + 固定出口」暴露面更大，建议后续收紧 `pg_hba` / 防火墙
6. 回滚素材保留在 102：dump 在 `/tmp/aisoc-db-migrate-20260823-021834/`，
   旧 .env 在 `src/backend/.env.bak.dbswitch.20260823-022120`。**旧远端库未删、数据完整冻结**，
   回滚 = 复原 .env + restart（脚本里已内置失败自动回滚路径）

### 待办（不阻塞）
- 旧远端库 `111.228.57.2:25432/AI-miniSOC-db` **暂不要删**，观察 1~2 周确认无回滚需求后再处理
- 本机库**目前没有备份机制**（原远端库是否有备份未知）→ 建议加 `pg_dump` 定时 + 保留策略，
  这是本次迁移引入的新风险点：数据从「别人运维的库」变成「自己运维的库」
- `pg_hba` / UFW 收紧 5432 访问源

---

## 今日补充（2026-08-26：P3+ 资产发现与攻击面扫描采集器 Phase 1+2 全量落地）

### 背景与设计
用户需求：① 扫内网发现未纳管资产 ② 扫台账公网资产暴露面端口/服务。
经 v1.0 初稿 → v1.1（发现/台账解耦）→ v1.2（控制面/数据面分离+拉模型）→ v1.3（评审修复）→ final 整合稿：
- `docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md`（单一权威稿）
- `docs/design/2026-08-26-control-plane-prototype.html`（5-tab 交互原型，CSS 变量自包含）
- `docs/design/2026-08-26-deployment-architecture.svg`

核心架构（ADR-6/7/8）：
- **发现/台账解耦**：scanner 落独立的 `soc_scan_findings`，**永不直接写 `soc_assets`**；
  台账写入仅限「一键纳管」`POST /scan/findings/{id}/adopt`（带权限带审计）
- **控制面/数据面分离 + 拉模型**：任务创建/调度/编排/看门狗全在 AI-miniSOC（102）；
  扫描器只做「心跳 + 拉任务 + 跑 nmap + 推数据 + 回写」——只出向请求，天然穿 NAT
- **扫描器显式注册**：admin `POST /scan/agents` 分配 scanner_id + API Key（sha256 哈希存库）

### 本次交付（commit 9304549 + 00d9216）

**后端（控制面）**：
- 4 张新表：`soc_scanner_tasks`（注意：类名 `ScannerTask`，`ScanTask` 被 vulnerability.py 占用！）/ `soc_scan_targets` / `soc_scan_findings` / `soc_scanner_agents`
- 2 个新 handler：`DiscoverySyncHandler`（data_type=discovery → findings）+ `PortSyncHandler`（data_type=port → asset_ports）；均镜像 AssetSyncHandler 的 sync_task+source_health 包装
- 15 个新端点（3 个 router）：`scan_agents`（扫描器 X-API-Key 4 个）/ `scan_human_agents`（admin 4 个）/ `scan_tasks`（人类 7 个含 adopt/ignore）
- `require_scanner_api_key`（deps.py）：X-API-Key → sha256 → soc_scanner_agents.api_key_hash 反查
- `scanner_watchdog_scheduler`：60s tick，L1 离线判定（90s）+ F-3 超时重派（6h，clone pending + parent_task_id，链上限 3 次）
- `central_scan_scheduler`：**固定秒数间隔**对齐每天 03:00/04:00（不引入 cron 字符串，v1.3 F-1）
- F1.3 扩展：`AssetReconciliationService.reconcile_scanner_findings()` —— 遍历 findings 产 `TYPE_SHADOW, asset_id=None, details.source="scanner"`，按 IP+24h 窗口去重；`run()` 主流程已调用，summary 加 `scanner_shadow_count`
- F4.2 场景 6：`check_scanner_offline()` + `DEFAULT_PUSH_RULES.scanner_offline`
- main.py lifespan：注册两个 scheduler + **`Base.metadata.create_all(engine)`**（此前启动不建表，新模型靠它即时落地）
- 迁移 `o1p2q3r4s5t6`：种 `/scan` 顶级菜单（sort=10）+ scanners/tasks/findings 3 子菜单 + 4 角色 × 授权（viewer/auditor 只读）

**采集器（数据面）**：
- `MiniSOCClient` 新增 4 方法：`heartbeat` / `fetch_pending` / `claim` / `report_status`（复用 envelope 解包 + 重试）
- `src/collectors/scanner/`：ScannerCollector + nmap_runner（XML 解析容错）+ run_scanner.py
  - `--once`：单次扫（cron/调试）
  - `--loop`：拉模型（30s 心跳 + 10s 拉任务 + 认领 + nmap + 推数据 + 回写）
- docker-compose 加 `scanner-collector` service（bridge + NET_RAW，init:true）

**前端**：routesAlias 加 5 个 alias（AssetScan/Scanners/Tasks/Findings/Targets）；页面渲染留 Phase 3

### 验证（全部实测）
- 单元测试 **35/35**：test_port_sync_handler.py 16 + test_reconcile_scanner.py 12 + test_port_sync_e2e.py 7
- 本地端到端 dry_run 11/11（/tmp/dry_run_phase2.py）
- **生产（102）端到端 11/11**：登录→注册 scanner→心跳 online→空任务→建任务→拉任务→claim→推数据 created=1→report→详情→清理
- 生产 DB 实查：4 张表 EXISTS、菜单树 4 条、`scanner:ports success=1`、scanner_tasks/asset_ports 落库
- 迁移 `o1p2p3q4r5s6 → o1p2q3r4s5t6` 生产实跑成功（head 已同步）

### 踩过的坑（本轮新增，后续必看）
1. **`ScanTask` 类名被 `vulnerability.py` 占用**——新模型必须叫 `ScannerTask`（final.md 硬伤 2 的预言成真）
2. **`ScanFinding.matched_asset_id` 类型必须是 UUID**（与 `Asset.id` 一致），第一版写成 BigInteger 导致 `DatatypeMismatch`，已修
3. **`AuditLog` 在 `app.models.audit_log`**，不在 asset_reconciliation（又一次手滑 import）
4. **alembic 迁移三连坑**（o1p2q3r4s5t6 实跑才暴露）：
   - `op.execute(text, params)` 双位置参数不兼容 → `bind = op.get_bind(); bind.execute(...)`
   - `:perms::jsonb` 与 SQLAlchemy 绑定冲突（`::` 被当参数）→ `CAST(:perms AS jsonb)`
   - `soc_role_menus` 没有 `created_at/updated_at` 列（CLAUDE.md 既有坑重踩）
5. **GitHub secret scanning 把文档示例 `sk_live_xxx...` 误判为 Stripe key 拒 push**——示例 key 改成
   `<由控制面返回的明文 Key>` 占位符 + amend 重写 commit 才过。**文档里别用 sk_live_ 前缀的假 key**
6. **测试链路三件套**（conftest 改动）：
   - `MCP_SSE_ENABLED=false`（否则后台线程抢 8100 端口 → SystemExit(3) 干扰 pytest）
   - `app.router.lifespan_context = noop`（否则 TestClient 跑 lifespan → stop_* 空 await 崩 teardown）
   - `Settings.collector_api_keys_list` 是 property，mock 用 `patch.object(type(settings), ..., new_callable=PropertyMock)`
7. **conftest 的 `from app.models import (...)` 是显式子集**——新模型必须加进列表，否则 create_all 漏建表
8. **envelope 断言口径**：X-API-Key 缺失是 422（Header 必填）不是 401；业务码全看 `body.code` 不看 HTTP status
9. **`Asset` 字段名是 `name` 不是 `asset_name`**（schema 里看着像，实际不是）
10. **测试 fixture 不自动 commit**：`_handle_one` 后必须手动 `db_session.commit()` 才能查到
11. **`reconcile_scanner_findings` 里 `finding_status=new + matched_asset_id=None` 才产 shadow**；
    `known` 且无 matched 视为脏数据也产 shadow 让人处置（测试期望与之一致）
12. **102 的 venv 在 `src/backend/venv`**（不是仓库根 venv）；ssh 跑 python 用 `./venv/bin/python`
13. **后台 scheduler 线程里不能 `_asyncio.run(svc._push(...))`**——uvicorn 已有 event loop，
    会 RuntimeWarning: coroutine was never awaited，通知静默丢失。修法：watchdog 只改状态，
    通知统一交给 push_scheduler（async 主线程）调 check_xxx()；过滤条件要查 `status='offline'`
    而非 `!= 'offline'`（否则 watchdog 标红后 push 永远查不到），重复推送靠 _push 的 dedup_title 挡
14. **裸机 PYTHONPATH 跑 scanner（docker.io 被墙时的备选）**：collector.py 用
    `from nmap_runner import ...` 绝对导入会失败，必须 `from .nmap_runner import ...` + fallback；
    Kali 上 `pip3 install --user --break-system-packages httpx pyyaml python-dotenv` 即可
15. **前端按钮权限必须种在「子菜单」自己的 permissions 上，不是父容器**：
    `hasAuth(authMark)` 读当前路由（子菜单）的 `meta.authList`（来自 soc_menus.permissions）。
    o1p2q3r4s5t6 第一版把 scan_run 等全种在父容器 /scan，子菜单 perms=[] 导致
    `v-if="hasAuth('scan_run')"` 恒 false。修复迁移 p1q2r3s4t5u6：子菜单各自写 permissions。
    同时**父容器（有 children）的 component 必须是 `/index/index`（Layout）**，不能写 `/scan/index`。
16. **`git bundle create A..B` 报 "Refusing to create empty bundle"**——即使 `git log A..B`
    显示有 commit（原因不明）。应急直接全量 `git bundle create /tmp/full.bundle master`（5.9M），
    102 端 `git fetch /tmp/full.bundle master:refs/remotes/bundle/master` 拿到目标 commit 再手动 deploy。

### 生产真实部署（2026-08-26，192.168.0.45 Kali）
- docker.io 被墙拉不到 python:3.13-slim → 走裸机方案（Kali 自带 nmap 7.95 + python3）
- 代码 scp 到 ~/scanner-collectors/，.env 注入 SCANNER_ID/MINISOC_API_KEY(=scanner Key)/MINISOC_URL
- **首次真实扫描**：nmap -sV -Pn --top-ports 1000 192.168.0.102 → 7 items → /data/sync created=6 updated=1
  （用扫描器自己的 Key，require_api_key 双收修复验证通过）；生产库实见 10 端口含 OpenSSH 9.6p1/nginx 1.24/PostgreSQL/Uvicorn
- **--loop 常驻**：30s 心跳 200，控制面 status=online；杀进程后 90s 看门狗标 offline
- **离线通知**：修复线程 async bug 后，手动 push-check 返回 scanner_offline=2，通知表落库
- scanner 已恢复 online（pid 244932 在 0.45 常驻）
- 待办：裸机是 nohup 临时方案，后续应配 systemd unit 或解决 docker mirror 后回容器

### 待办（不阻塞，按优先级）
1. ~~部署 192.168.0.45（Kali）真扫描器~~ ✅ 已完成（裸机 --loop 常驻，心跳/离线/通知全验证）
2. **`/data-health` 展示 scanner:* 键**：DB 有记录（success=2）但端点展示层未覆盖新键，小 PR 补键清单
3. ~~Phase 3 前端~~ ✅ 已完成（2026-08-26 commit 49f80bd）：scanners/tasks/findings 3 页面 + api/scan.ts + 迁移 p1q2r3s4t5u6；生产验证菜单 authMarks/API/scan chunk/nginx 200 全过。待人工浏览器点一遍 UI
4. **生产 overall=degraded 是既有问题**：loki:browsing_detection 自 08-18 未跑，与本次无关
5. **双 Key 收口**：Phase 1 让 scanner 共用 `MINISOC_API_KEY`；Phase 4 改独立 `SCANNER_API_KEY`（require_scanner_api_key 已就绪，只差 env 下发）
6. **run_daemon.py 旧守护逻辑**与 docker restart 重叠，建议评估删除（续三遗留）
7. **0.45 scanner 裸机 nohup 临时方案**：后续配 systemd unit 或解决 docker mirror 后回容器

---

**文档版本**: v2.26
**最后更新**: 2026-09-06

---

## 今日补充（2026-09-06：行为画像全量落地 + 入口跳转）

### 本次交付

**方案**：`docs/design/2026-09-05-用户IP行为画像-方案设计.md`（v1.5，~600 行，§9 落地方案含 9.7.1–9.7.9 修复清单）
**原型**：`docs/reports/2026-09-05-行为画像-原型设计.html`（5 主体 × 4 Tab 全量渲染，附附录 C 已知问题清单）

### 9 个 commit 速查

| Commit | 内容 |
|--------|------|
| `0353abc` | Phase 1.5 落地（快照表 + 服务模块 + 水位回溯） |
| `59812a0` | Phase 2 产品化（API + 前端 + 菜单 + MCP） |
| `b21603a` | fix: service 误用 Asset.asset_name → .name（CLAUDE.md P3 坑 #9） |
| `7d9e772` | Phase 3 AI 增强（LLM 解读 + F4.2 场景8 推送） |
| `89495bc` | 四 Tab 全量 + 身份管道 Phase 0 + B2/B3 批次 |
| `69f55ff` | fix: 身份管道分批 + 风险榜 level→level_max |
| `110547e` | fix: 身份管道预加载已有文档id+关autoflush+每250条 |
| `4caa4cf` | fix: 身份管道 pending 绑定内存去重 |
| `0c9a504` | fix: 画像图表空白——echarts 在 0 宽容器 init 时序 |
| `eb911f6` | fix: 脚本块多余大括号 |
| `a755750` | **本批**：列表页 IP 列点击跳画像页（入口联动） |

### §9 验收核对（方案 §9.9）

- ✅ 活跃时段分布（原始日志逐条计数，口径已固化在 `loki_source.py`）
- ✅ 行为节律 7 时段占比 + 星期×小时热力（ECharts heatmap，行为 Tab 第 3 卡）
- ✅ 域名 TOP N + 下钻到日明细
- ✅ 14 类兴趣分类（**新增"学习教育"类**让"学生党"标签可触发）
- ✅ 画像标签（PERSONA_MAP：夜猫子→野猫子、周末战士→工作狂）
- ✅ 机器流量自动折叠/降权（traffic_type=human/machine/mixed）
- ✅ 快照留存 ≥180 天（`soc_behavior_profiles`+`soc_behavior_domains`）
- ✅ 主体键 `(asset_id, profile_date)`，DHCP 漂移不分裂
- ✅ 断点补拉 + `status='gap'` 显式缺口标记（防假绿）
- ✅ 告警分级阈值 import `app.core.alert_levels`（13/10/7/4）
- ✅ X1 矩阵：读端点 admin+auditor，refresh 走 `require_button_permission`
- ✅ 审计留痕：所有查看行为写 `soc_audit_logs`（`resource_type=behavior_profile`）
- ✅ 合规水印「本数据仅用于安全审计」+「仅输出信号不定性」
- ✅ 入口跳转（资产/告警/上网行为 → 画像，§9.5）

### 9.7.1–9.7.9 修复落点

| # | 修复 | 落地位置 |
|---|------|----------|
| 9.7.1 | traffic_type 自动判定（SYS≥60% → machine） | `aggregator.compute_traffic_type()` |
| 9.7.2 | 快照表突破 Loki 7 天 | `soc_behavior_profiles`+`_domains` |
| 9.7.3 | 分类词典可配置 | `classifier.py` 读 `soc_system_config.domain_categories` |
| 9.7.4 | PERSONA_MAP 规则→人设解耦 | `tagger.py` PERSONA_MAP 字典 |
| 9.7.5 | 新增「学习教育」分类 | `classifier.CATEGORIES["学习教育"]` |
| 9.7.6 | IP≠人，明示"设备画像"+关联账号入口 | 身份管道 Phase 0（已上线） |
| 9.7.7 | 原始日志逐条计数（禁用 count_over_time） | `loki_source.py` 注释约束 + 写死 |
| 9.7.8 | 主体键 `(asset_id, profile_date)` | 模型 `UniqueConstraint` |
| 9.7.9 | 断点补拉 + gap 占位 | `snapshot_job.mark_gap()` + `BehaviorProfileWatermark` |

### 入口跳转实现要点（`a755750`）

**入口侧**（IP 列变 ElLink/可点击）：
- `views/asset/list/index.vue` — asset_ip 列 → ElLink
- `views/alert/list/index.vue` — agent.ip 列 → ElLink（需新增 `useRouter`）
- `views/browsing/baseline/index.vue` — baseline ip 列 → `<a>` click
- `views/browsing/event/index.vue` — event ip 列 → `<a>` click（需新增 `useRouter`+`h`）

**出口侧**：`views/browsing/profile/index.vue` onMounted 读 `route.query.ip / agent_ip`，
若在 `subjects` 列表则自动 `selectSubject(ip)`。`stopPropagation` 防行点击穿透。

### 踩坑（本批+前批，4 条核心）

1. **`useRouter` 必须在 setup 顶层声明**——`useTable` 的 `columnsFactory.formatter` 是普通函数，没有 setup 上下文
2. **`<component :is>` 会渲染 `formatter(row)` 返回的对象**——art-table 已支持（`isObject()` 判断分支），返回 `h(ElLink,...)` 即可
3. **baseline/event 原本只 import `useTable`**——需补 `h` 和 `useRouter`，否则 vue-tsc 报 no-unused-vars
4. **`route.query` 要在 onMounted 里读**——setup 顶层读时 subjects 还没加载完，`some()` 永远 false 失效

### 测试入口

- 画像列表页：菜单「上网行为」→「行为画像」→ 左侧栏选主体 → 四 Tab
- 入口跳转：① 资产管理→点任意 IP ② 告警管理→点告警 IP ③ 上网行为→基线/事件→点 IP，均跳过来
- 实时刷新：标识条右上「实时刷新」按钮（v-auth=refresh，仅 admin/operator 可见）
- AI 解读：「AI 解读」按钮（GLM 降级会显示"规则模板（AI 不可用降级）"）
- 导出：标识条「导出」按钮 → 自包含 HTML（含合规水印，浏览器可直接打开）

### 待办（不阻塞）

- 9.7.3 分类词典表独立化（当前是 soc_system_config JSON 字段，量大了再抽表）
- 历史快照补跑（生产已跑通 9/5 当日，之前日期因 Loki 已过窗需 status=gap）
- Phase 4 双 Key 收口（scanner 独立 SCANNER_API_KEY）

---

**文档版本**: v2.26

---

## 今日补充（2026-09-06 续：行为画像两层结构改造实施）

### 本次交付（方案 `docs/design/2026-09-06-行为画像-两层结构改造方案.md` v1.2，S1-S7 全落地）

**结构**：菜单「行为画像」从"单 IP 详情页塞主体列表"拆成两层——
- **L1 群体概览** `/browsing/profile`（重写 `profile/index.vue`）：KPI 卡（主体总数/人类/快照天数/低置信度数）+ 人设分布条形（可点筛列表）+ 全网 24h/时段/兴趣/风险分层四图 + 主体列表（traffic_type/conf/搜索/四列排序/分页，行点击进 L2）
- **L2 单 IP 详情** `/browsing/profile/detail/:ip`（新建 `profile/detail.vue`）：左栏**身份档案卡**（基本信息/归属/关联账号双向钻取/数据来源新鲜度色标/画像摘要，sticky 不随 Tab 消失）+ 面包屑 + IP 切换下拉 + 原 4 Tab
- **D2 修复**：关系 Tab 新增 ECharts graph 力导向拓扑（入站蓝/出站绿/攻击源红/同网段灰虚线，边粗细按次数对数映射，>30 节点自动切环形，节点点击跳对方画像）；`relations` 接口补 `same_segment`（已滤 0.0.0.0/127.0.0.1）
- **D3 根因确认**：`len(ok_rows)>=4` 硬门槛 + 仅 1 天快照，非 bug；S7 核实 top_rules 非 bug（.102 实测 8 条，空数组仅无 agent 设备的正常空态）

**后端**：`GET /behavior-profile/overview?days=7`（admin+auditor+审计，主体级取最近 ok 快照、全网聚合取窗口内快照求和、风险分层用 criticality）；`get_profile` asset 补 business_unit/data_source/last_synced_at/criticality

**S6 traffic_type 修复**（方案 §2.3 的真问题）：
- classifier 系统背景层补机器心跳/组网打洞域名（stun/easytier/tailscale/zerotier/ddns/ipw.cn/fnnas/whoami/oray 等）——.17 NAS 的 SYS 占比从 8.9% → 81.5%
- `compute_traffic_type` 加双辅助判据：SYS≥50% → machine；SYS≥30% 且 TOP3 域名集中度≥50% 且 24h 变异系数≤0.15 → machine；mixed 需 SYS 参与（防邮箱心跳类人类设备误判）
- **POC 四主体回归全过**：.17→machine；.8 Mac（top3 98.9% 但 SYS 0.2%）/.100（CV 0.055 但 SYS 0%）/.25（CV 1.2）→ human
- **生效时间**：次日起的新快照（存量快照 layer_visit 是旧词典算的，不改写历史）

**迁移 `b1c2d3e4f5g6`**（down_revision=z6a7b8c9d0e1）：插隐藏菜单 `profile/detail/:ip`（component=/browsing/profile/detail，is_visible=false）+ 授权自动派生自「行为画像」菜单持有角色（admin+auditor）；downgrade→upgrade 循环幂等已验

### 踩坑（本轮新增）
1. **SQL 里 `:ip` 路径字符串会被 text() 当绑定参数**——验证查询报 "A value is required for bind parameter 'ip'"（`:perms::jsonb` 同款坑）。用 `"profile/detail/:" + "ip"` 拼接或参数化传值
2. **`Asset` 没有 `hostname` 列**（name/asset_ip/mac_address…），第一版 same_segment 查询带了 hostname 直接炸；写查询前先确认列存在
3. **compute_traffic_type 的辅助判据必须要求 SYS 参与**：纯"集中度+平直"会把邮箱客户端心跳（top3 98.9%）的人类设备判成机器——.8 就是活例子
4. **模拟数据验证判据不可靠**：第一轮用随机数模拟 by_hour，.8/.25 全被误判 mixed；必须用 POC 真实 by_hour 数组回归
5. **menu component `/browsing/profile/detail` 直接命中 detail.vue**（ComponentLoader 先试 `path.vue` 再试 `path/index.vue`），不需要建目录/index.vue——与资产详情（/asset/detail/index 是目录）两种形态都支持

### 待办（不阻塞）
- ~~生产部署后需手跑 `alembic upgrade head`（b1c2d3e4f5g6）~~ ✅ 已于 2026-09-06 19:52 执行（连跑 z6a7b8c9d0e1 + b1c2d3e4f5g6，生产 /browsing 父菜单 component 修复同时生效；隐藏菜单 id=69，授权 admin+auditor）
- 验收 #7（异常判定核心规则）待快照积累 ≥4 天
- .17 立即变 machine：可删其窗口内旧快照让水位重拉（未做，避免改写历史）
- 拓扑图图例筛选（方案 §6.3 V2 项）

---

## 今日补充（2026-09-06 续二：L1 主体列表首屏不可见修复 + 排查记录）

### 用户反馈
「行为画像页面没有显示原型中的画像主体列表，进不了具体 IP 的详情界面」。

### 排查过程（证据链，未复现"列表缺失"本体）
1. **生产 DB/服务层全绿**：146 快照/73 IP/overview+list 服务层直调正常；菜单 68(profile)+69(隐藏 detail) 组件/授权正确
2. **生产静态资源全绿**：index.html 引用资源全部 200，dist 含新页面字符串
3. **生产审计表定时间线**：今天仅 13:43 有 5 条旧版页面请求序列（list+profile+trend+anomalies+risk，无 overview）；**19:46 部署后零审计零 LOGIN = 用户部署后没在生产打开过** → 用户看的是本地 5173
4. **本地 5173 无头浏览器实测（puppeteer-core + 系统 Chrome）**：L1 一切正常——KPI/人设分布/列表 15 行(共74条)全渲染，dispatch click 行 → detail 跳转成功，L2 身份档案+4Tab 正常
5. **根因**：主体列表排在 5 个图表区块之后（人设分布/节律/兴趣/时段/风险），真实页面这些卡片很高，**列表被推出首屏**——L1→L2 唯一入口首屏不可见，用户未滚动即得出"没有列表"

### 修复（commit d34ed95，已部署生产 12:33）
- **布局重排**：KPI → **画像主体列表**（主入口）→ 图表洞察区。列表卡片首屏 236px 处完整可见（实测）
- 列表空数据 ElEmpty 兜底（区分"筛选无匹配" vs "无快照/无权限"）
- 无迁移、纯前端

### 无头浏览器实测登录注入法（后续可复用）
`document.querySelector('#app').__vue_app__.config.globalProperties.$pinia._s.get('userStore')`
→ 直改内存 accessToken/isLogin/info → location.hash 导航（守卫放行 + 动态路由注册走真实流程）。
注意：store id 是 `userStore` 不是 `user`；reload+localStorage 注入会被 401 轮询竞态清掉，不可靠。

### 踩坑
1. **入口型组件不能排在洞察型图表后面**——列表/按钮是"下一步动作"，图表是"看完的洞察"；首屏（~1000px）必须看到主入口
2. **puppeteer page.click 坐标点击对长页面元素会失败**（elementFromPoint null），dispatchEvent MouseEvent bubbles:true 可靠
3. **生产排障先查审计表时间线**：soc_audit_logs 的 action 序列能还原用户实际访问了哪些接口、什么版本（旧版序列 list+profile+trend vs 新版 overview），比猜环境快得多
4. **登录验证码后端不强制**（不带 captcha_key 字段直接放行；带 key 才校验）——前端表单必填挡了个寂寞，**安全洞待修**（见下）

### 待办（新发现，不阻塞）
- **登录验证码可绕过**：POST /auth/login 不带 captcha_key/captcha_code 即跳过验证（实测 curl 200 拿 token）。建议后端对启用验证码的配置强制校验，或前端 captchaEnabled 与后端配置对齐
- 无头浏览器 e2e 脚本沉淀到 scripts/（当前在 /tmp/pptr，含登录注入/首屏断言/点行跳转）
