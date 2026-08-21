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

### Alembic 迁移历史不完整（2026-08-19 更新）
- 生产库 `soc_menus.component` / `permissions` 列是手工 ALTER 加的，alembic 历史漏写迁移
- 后果：`alembic upgrade head` 在空库必败；`alembic check` 一直 WARN（CI 里是 advisory）
- 另外 `soc_source_health` 等 8 张 P4 表在 model 但不在迁移链
- **当前对策**：CI 用 `scripts/ci_create_tables.py`（Base.metadata.create_all + 补列）建测试库；生产 schema 与 model 一致（head=a0b1c2d3e4f5）
- **待修**：补一个迁移把这些表/列写进历史，之后 `alembic check` 才能改阻塞

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
- **数据库**: 远端 PostgreSQL 111.228.57.2:25432；**生产库 `AI-miniSOC-db`**（服务器 .env 指向）；本地 Mac dev 用 `AI-miniSOC-testdb`；pytest 专用 `AI-miniSOC-db_test`——三个库严格分离，**本地 .env 绝不指向生产**
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

**文档版本**: v2.4
**最后更新**: 2026-08-21
