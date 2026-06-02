# AI-miniSOC 项目开发指南

这个文件为 Claude Code (claude.ai/code) 提供 AI-miniSOC 项目开发时的上下文和指导。

## 项目概述

AI-miniSOC 是一个**AI驱动的微型安全运营中心**，集成了日志聚合、威胁检测、主机监控和AI分析能力。

当前开发环境位于 `/Users/xiejava/AIproject/AI-miniSOC`

## 技术栈

### 后端 (Backend)
| 技术 | 版本/说明 |
|------|----------|
| Python | 3.14 |
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
│   │   │   ├── api/          # API路由 (auth, users, roles, menus, departments, assets, ...)
│   │   │   ├── core/         # 核心配置、认证、验证码、响应包装中间件
│   │   │   ├── models/       # SQLAlchemy 模型 (19张表)
│   │   │   ├── schemas/      # Pydantic Schema
│   │   │   ├── services/     # 业务逻辑层
│   │   │   └── database.py   # 数据库连接
│   │   ├── alembic/          # 数据库迁移
│   │   ├── main.py           # FastAPI 入口
│   │   └── .env              # 环境变量 (不上传Git)
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
| 同步任务 | `app/api/sync.py` | 资产同步 |
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
| soc_assets | 资产表 |
| soc_asset_ports | 资产端口表 |
| soc_asset_tags | 资产标签表 |
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
| asset_change_logs | 资产变更日志表 |
| sync_tasks | 同步任务表 |

> 实际共 **20 张表**（`from app.models.base import Base; len(Base.metadata.tables)`）。

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
- **OpenSearch**: 192.168.0.30:9200

#### Loki 日志系统
- **位置**: http://192.168.0.30:3100
- **配置**: /etc/loki/config.yaml
- **保留策略**: 7天
- **最大查询**: 500天 (12000小时)
- **存储**: /data/loki

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
- `service_name`: 服务名称

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

### 启动开发服务器
```bash
# 后端 (从 src/backend/ 目录启动以正确加载 .env)
cd src/backend
../../venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd src/frontend
npm run dev        # 开发服务器: http://localhost:3006
npm run build      # 生产构建
```

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

### Alembic迁移
- `alembic_version` 表引用了一个不存在的修订版本
- 当前使用直接SQL/SQLAlchemy创建表作为替代方案（见 `src/backend/scripts/create_missing_tables.py`）
- 实际已能 create_all（通过 Base.metadata）正常启动

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
- [ ] 补全项目文档
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

---

## 今日补充（2026-06-02 session 续记）

> 本节由 Claude 续写，记录 5/29 后到 6/2 期间本会话发现的项目状态变化。

### 关键变更
- **API 模块从 11 个 → 18 个**：新增 dicts / system_configs / asset_ports / asset_tags / asset_incidents / deps 等
- **数据表从 19 → 20**：新增 `soc_dicts`（字典管理）
- **Phase 1 进度约 87%**：审计日志前端、字典管理、系统配置、JWT 硬化、独立测试库、头像兜底已完成
- **Git 分支**：项目**只**用 `master`，没有 `develop`/`main`，也**不**用 `<type>(<scope>)` 前缀

### 测试基线（2026-06-02 建立）
- `tests/test_token_blacklist.py`（unit, 8 个）：token 黑名单模块
- `tests/test_auth_api.py`（E2E, 12 个）：登录锁定 / refresh 轮换 / logout 黑名单，走 live uvicorn
- `tests/test_users_api.py`（2 个）：in-process TestClient
- **总计 44 in-process 测试 pass**（pre-existing 的 `tests/integration/test_user_workflow.py::test_user_lifecycle` 仍 fail，是 envelope 设计 vs 断言风格不匹配，未在本次范围）

### 本次未做但建议尽快处理
1. `ENCRYPTION_KEY` 修成合法 Fernet 密钥（pre-existing 启动 warning，重启丢加密数据）
2. 修 `tests/integration/test_user_workflow.py` 的 envelope 断言

---

**文档版本**: v2.1
**最后更新**: 2026-06-02
