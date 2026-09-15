# AI-miniSOC — Claude 工作指南

> **本文件每次 session 启动被完整注入到上下文**。它的价值 = 决策支持 − 噪音。
> 第一性原理：只记录「无之则下次必踩坑」的硬约束；可机器验证的事实由 `scripts/sync_claude_md_truth.py` 自动同步（见 §0）。
> **不要往这里 append session 笔记**——新写法见 §5。

---

## 0. 项目硬事实（必读入口）

> 这些是**每次 session 必查**的事实，但**不能手抄**——所以由脚本同步。

**最权威快照**：[`docs/project-truth/snapshot.md`](docs/project-truth/snapshot.md)

| 事实 | 当前值 | 来源 |
|---|---|---|
| 业务表数 | 66（全部 `soc_` 前缀） | `Base.metadata` |
| alembic 迁移文件 | 62 | `alembic/versions/` |
| **alembic heads** | **2 个**（`r4s5t6u7v8w9`, `v7w8x9y0z1a2`） | `alembic heads` |
| 顶级菜单 | 11 个 | `soc_menus WHERE parent_id IS NULL` |
| X1 角色 | admin / operator / viewer / auditor（+ 历史 user/readonly/test_role） | `soc_roles` |
| Wazuh URL | https://192.168.0.40:55000 | `.env` |
| OpenSearch URL | https://192.168.0.40:9200 | `.env` |
| Loki URL | http://192.168.0.30:3100 | `.env`（**当前不可达**，见 §4） |
| 生产 DB | 本机 `192.168.0.102:5432`（PG 16.15，库 `AI-miniSOC-db`） | 服务器 `.env` |
| 本地 dev DB | 远端 `111.228.57.2:25432` 库 `AI-miniSOC-testdb` | Mac `.env` |
| 测试 DB | `AI-miniSOC-db_test`（独立库） | `TEST_DATABASE_URL` |

**关键警告**：
- **alembic 是 2 个 head**——CLAUDE.md 老版本一直说"单 head 线性"是过期的。**升级前必须先确认哪个是真正要追的 head**，或先 merge 迁移线。
- 部署时**本地 Mac 的 `.env` ≠ 生产服务器 `.env`**——前者连远端 testdb，后者连 102 本机生产库。改 env 必须两处都改。

**如何更新本快照**：
```bash
venv/bin/python scripts/sync_claude_md_truth.py
```
脚本会重新生成 `docs/project-truth/snapshot.md`。CI 应跑这个脚本校验 diff，发现手抄偏差立即报警。

---

## 1. 必读约束（每次写代码都触发）

> 这些是**项目结构性约束**，违反就出 bug 或安全洞。

### 1.1 后端 envelope 响应格式

**所有 API 响应统一为** `{"code": 200, "msg": "success", "data": <payload>}`。

- 成功 → `code = 200`
- 错误 → `code = 401/403/404/422/500` 等，**HTTP 状态码恒为 200**
- 实现：`src/backend/app/core/response_wrapper.py`
- **前端 axios 拦截器只读 `body.code`，不要读 `response.status`**
- 422 (Pydantic 校验失败) 会被包装成 HTTP 200 + `code=422` + `data=None`——**这是 CLAUDE.md 老版本说"假阴性/假绿"的根因之一**

### 1.2 表命名强制 `soc_` 前缀

所有业务表必须 `soc_` 前缀（CLAUDE.md 老版本反复强调的"建表走 alembic 不要 create_all"就是为了保这个）。`alembic_version` 是唯一例外。

### 1.3 权限矩阵 X1

- 4 角色：**admin / operator / viewer / auditor**
- 端点级守卫：`require_role(*codes)` + `require_button_permission(menu_path, auth_mark)`
- 实现：`src/backend/app/core/permissions.py`（admin bypass）
- **菜单树粒度**：子菜单须自身被授权，父菜单只是容器——`get_menu_tree` 修过这个 bug（见 §5 索引 L967）
- 写端点默认 admin only；operator/viewer/auditor 需逐端点授权（X1 表）
- X1 全量落地回顾：[索引 §权限矩阵 X1](docs/sessions/INDEX.md#权限矩阵-x1)

### 1.4 告警分级阈值

**全项目唯一权威**：[`src/backend/app/core/alert_levels.py`](src/backend/app/core/alert_levels.py)

```python
LEVEL_CRITICAL = 13
LEVEL_HIGH = 10
LEVEL_MEDIUM = 7
LEVEL_LOW = 4
LEVEL_NOISE_BELOW = LEVEL_LOW  # <4 视为噪音不计入
SEVERE_LEVEL = 12  # 通知阈值（与 LEVEL_HIGH 是不同语义）
```

**禁止裸数字比较**——一律 `from app.core.alert_levels import LEVEL_*`。`AlertQueryService.LEVEL_*` 是 re-export 兼容。

### 1.5 审计日志走 hash 链

`AuditLogService.create_audit_log()` 写 `soc_audit_logs`，每条带 `log_hash` + `prev_log_hash` 形成链。**任何用户操作都通过 `@log_audit` 装饰器落链**——不要绕开。

### 1.6 关键 API 路径惯例

- 所有 API 统一前缀 `/api/v1`
- 响应包装：`{code, msg, data}`（见 §1.1）
- **envelope 中间件会跳过** `/docs` / `/redoc` / `/openapi.json` + 非 `/api` 路径
- 路由级 `prefix=` 与 endpoint 路径**不要双重前缀**（F2.2 教训）
- 端点矩阵的当前真值由脚本读 `app/api/` 推断——下一版快照会加

### 1.7 部署三库严格分离

| 库 | 用途 | .env 位置 |
|---|---|---|
| `AI-miniSOC-db` | **生产**（192.168.0.102 本机） | 服务器 `/home/xiejava/AIproject/AI-miniSOC/src/backend/.env` |
| `AI-miniSOC-testdb` | **本地 Mac dev** | Mac 本仓库 `.env` |
| `AI-miniSOC-db_test` | **pytest**（独立库） | `TEST_DATABASE_URL` env 覆盖 |

**绝对不要**让本地 `.env` 指向生产库。`sync_claude_md_truth.py` 会同时验证。

---

## 2. 部署拓扑速查

> 这部分是**改配置 / 排错时必查**——脚本会自动重写以保持新鲜。

### 2.1 内网服务地址（生产 192.168.0.102）

| 服务 | 地址 | 备注 |
|---|---|---|
| AI-miniSOC 后端 | http://192.168.0.102:8000 | systemd `aisoc-backend` |
| AI-miniSOC 前端 | http://192.168.0.102:8080 | nginx 服务 dist/ |
| PostgreSQL | 192.168.0.102:5432 | 本机 PG 16.15（**不是远端**！） |
| Wazuh API | https://192.168.0.40:55000 | 旧记 `.30` 已过期 |
| OpenSearch | https://192.168.0.40:9200 | 同上 |
| Loki | http://192.168.0.30:3100 | **当前不可达**——`browsing_detector` 持续降级 |
| Grafana | https://grafana.xiejava.dpdns.org | 反代 |

### 2.2 CI/CD

- CI：GitHub 托管 runner（`ci-backend.yml` / `ci-frontend.yml` / `unit-tests.yml`）
- CD：装在 102 的 **self-hosted runner** `aisoc-prod-deployer`（label `prod-deployer`）
- 触发：`push master` → CI 全绿 → CD 自动部署
- 入口脚本：`deploy/deploy.sh`（含 fetch depth+timeout / pip / vite build / systemd restart / HTTP+DB 双探活 / 失败全局 trap 回滚）
- 部署日志：`/tmp/aisoc-deploy.log`（服务器）
- 后端日志：`/var/log/aisoc/backend.log` + `journalctl -u aisoc-backend`
- ⚠️ 102→GitHub 慢网 ~456 B/s，fetch 已限 depth+timeout；大文件走 `git bundle + scp` 备选
- **采集器 (`src/collectors/`) 之前完全在 CI/CD 外**——已由 `deploy/deploy_collectors.sh` 补齐（2026-08-23）

### 2.3 关键运维命令（服务器 102）

```bash
# 后端（systemd，免密 sudoers）
sudo -n systemctl status aisoc-backend
sudo -n systemctl restart aisoc-backend
tail -f /var/log/aisoc/backend.log

# 手动部署指定 commit（不经 GitHub Actions）
bash deploy/deploy.sh <commit_sha> "说明"

# runner
sudo systemctl status actions.runner.*
```

### 2.4 本地 Mac dev

- 后端 venv 在 `venv/`（**不是 src/backend/venv**——CLAUDE.md 老版本错记）
- 启动：`cd src/backend && ../../venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload`
- 前端：`cd src/frontend && npm run dev` → http://localhost:5173
- 测试库：`CREATE DATABASE "AI-miniSOC-db_test";`（如不存在）

---

## 3. 关键模块位置（按功能找代码）

> 这是**新需求落地时定位代码**的索引。每个文件位置是真读的，不是抄 CLAUDE.md 旧版。

### 3.1 后端核心

| 功能 | 文件 |
|---|---|
| Envelope 响应包装 | `src/backend/app/core/response_wrapper.py` |
| 权限矩阵 (X1) | `src/backend/app/core/permissions.py` |
| 告警分级权威 | `src/backend/app/core/alert_levels.py` |
| 审计 hash 链 | `src/backend/app/services/audit_log_service.py` |
| AI 限流/熔断 | `src/backend/app/services/ai_budget.py`（QPS=2, DAILY_CAP=500） |
| 配置中心 resolver | `src/backend/app/services/data_source_resolver.py` |
| 配置中心管理 | `src/backend/app/services/data_source_service.py` |
| Alembic 配置 | `src/backend/alembic/`（62 迁移，2 head） |

### 3.2 按业务域

| 业务 | 关键文件 |
|---|---|
| 资产管理 | `api/assets.py` + `services/asset_*.py`（risk/sync/summary/reconciliation/enrichment/lifecycle） |
| 资产扫描（scanner） | `api/scan_agents.py` + `api/scan_human_agents.py` + `api/scan_tasks.py` |
| 资产知识图谱 | `services/graph/` + `api/graph.py`（**builder 跑在线程里**，见 §4 教训） |
| 告警查询 | `services/alert_query.py`（**唯一权威 level 计数**——别自己数） |
| 风险评分 F1.1 | `services/asset_risk.py` |
| 资产稽核 F1.3 | `services/asset_reconciliation.py` + `api/asset_reconciliation.py` |
| 资产概览 | `services/asset_overview.py` |
| 数据健康 | `services/data_health.py`（源健康 + 同步死信 + 对账差异三层） |
| AI 查询 L1/L2 | `services/asset_query.py` + `services/query_templates.py` |
| AI 报告 F2.2 | `services/report_generator.py` |
| 变更影响分析 F3.1 | `services/impact_analysis.py`（**降级版**，无拓扑） |
| 行为画像 | `services/behavior_profile/`（含 `loki_source.py` / `classifier.py` / `tagger.py` / `identity/`） |
| 知识库 | `services/knowledge.py` + `api/knowledge.py` |
| 合规 F3.3 | `services/compliance.py` + `services/compliance_ai.py` |
| 上网行为检测 | `services/browsing_detection/`（**当前 Loki 不可达**，功能降级） |
| 系统配置 | `api/system_configs.py`（**注意**：旧称 advanced_config，9 月已重命名） |

### 3.3 前端核心

| 功能 | 位置 |
|---|---|
| 后端驱动菜单 | `src/frontend/src/api/menus.ts` + 路由 `router/routesAlias.ts` |
| 按钮权限 `v-auth` | `src/frontend/src/directives/auth.ts` + `useAuth()` hook |
| 表格封装（**必须用**） | `src/frontend/src/hooks/useTable.ts` + `ArtTable` + `ArtTableHeader` + `ArtSearchBar` |
| 角色管理页（**对齐基准**） | `src/frontend/src/views/system/role/index.vue` |
| 系统信息（动态 logo/名/版权） | `src/frontend/src/store/modules/system.ts` |
| 登录态 | `src/frontend/src/store/modules/user.ts`（pinia + persist） |

### 3.4 采集器（`src/collectors/`）

- 共享框架：`src/collectors/base/collector-framework`
- TP-Link 路由器：`src/collectors/tplink/`（Docker，**注意：8/23 修复了 `__main__.py` 多 asyncio.run bug**）
- Wazuh：`src/collectors/wazuh/`（**注意：8/23 修复了 `${VAR}` 占位符 bug**）
- 资产扫描：`src/collectors/scanner/`（nmap 数据面 + 控制面通过 `/api/v1/scan/*`）

---

## 4. 踩坑教训精选（重做相关功能时必读）

> 这些是**重做 / 排错 / 验证**时必读的——按"错误模式"而非时间排列。
> 完整 session 笔记按主题分类在 [`docs/sessions/INDEX.md`](docs/sessions/INDEX.md)。

### 4.1 envelope 假阴性 / 假绿

**根因**：HTTP 状态码恒 200，错误码在 `body.code`；中间件把 `data=None` 当 200 业务码包出。
**后果**：测试断言 `response.status_code == 201` 全失败；端点返回的"成功"实际是 422 校验失败。
**修复**：
- 前端 axios 看 `body.code`，别看 HTTP status
- 测试断言改 `body["code"] == 201` 或 `body["code"] in (200, 201)`
- 同步采集器 `sync_client` 把 `body.code=400` 当成功（持续假绿，已知未修）

### 4.2 计数类需求一律服务端聚合

**根因**：取 N 条文档客户端分桶 → N 大了关键告警被截断窗口外
**教训**：把 99 条 critical 报成 0 比查询失败危险得多——失败被看见，假阴性让人放心。
**唯一权威**：`AlertQueryService.get_level_buckets_by_ip()`（`size=0` terms 聚合）——**禁止复制别处实现**
**教训案例**：2026-08-22 F3.1 把 99/635 critical/high 报成 0/0 就是这个坑。

### 4.3 alembic 迁移的 4 条红线

1. **dry-run 不执行 INSERT**——`--sql` 模式下 Python 状态变量 + 回读 SELECT 全炸
2. **禁硬编码 id**——业务种子必须 JOIN 菜单/角色表，不存在时静默 0 行
3. **`op.execute(text, params)` 双位置参数不兼容**——用 `bind = op.get_bind(); bind.execute(...)`
4. **JSONB 用 `CAST(:x AS jsonb)`**——`:perms::jsonb` 会被当绑定参数
5. `soc_role_menus` 只有 `role_id/menu_id/permissions` 三列——**没有 created_at/updated_at**（老坑，9/14 还中招一次）

### 4.4 菜单 / icon 的静默失败模式

| 写法 | 后果 |
|---|---|
| `component='xxx/index.vue'` | 404（component 应是去掉 .vue 的路径） |
| 子菜单 `path='/xxx'` 带前导斜杠 | 拼成 `/parent//xxx` 双段 |
| `icon='Document'` / `'Settings'` | Material Font class，iconify 静默不渲染 |
| `icon='ri:git-compare-line'` | 该名**不存在**，iconify 静默不渲染 |
| 父容器 `permissions=[...]` | 子菜单 v-auth 恒 false |
| 父容器 `component='/<name>/index'` | 容器无 page.vue → 404，应用 `/index/index`（Layout） |

**icon 必须**：`ri:*` 格式 + 在 https://icones.js.org/ 真实存在。
**约定 C11**（设计文档）：icon 必须 iconify `ri:*` 且真实存在。
**约定 C12**：`soc_role_menus` 只有三列。

### 4.5 Graph builder 阻塞（最高优先级教训）

**根因**：`IdentityGraphBuilder` 等同步函数跑在 `@track_task async def` 里 → 占死 uvicorn 单 worker event loop → 全站 API 500/000。
**必修模式**（`app/services/graph/scheduler.py`）：
```python
def _run_builder_in_thread(fn, name, wait=...):
    # 工作线程内建 Session, try commit / except rollback / finally close
    # 杜绝僵尸事务 + 杜绝 event loop 占用

# 定时循环与 POST /graph/rebuild 都走 asyncio.to_thread
await asyncio.to_thread(_run_builder_in_thread, fn, name, wait=wait)
```
**关键决策**：用 `threading.Lock`（**不用** `asyncio.Semaphore`）——`@track_task` timeout 会 cancel 协程，asyncio 锁提前释放，但 to_thread 工作线程不可中断仍在写库。threading.Lock 随线程生命周期严格持有。

### 4.6 配置中心 11 个调用点的迁移

迁移后 `Settings` 中 `WAZUH_*`/`OPENSEARCH_*`/`LOKI_*` 等设为 `Optional[str] = None`——**否则 .env 移除键后 Settings ValidationError 启不来**。每次新增 env 键必须确认 Settings 字段已允许 None。

### 4.7 行为画像的两层主体键

主体键 `(asset_id, profile_date)`——DHCP 漂移不分裂画像。**`profile_date` 不可省略**。
**L1 vs L2**：L1 群体概览（KPI/列表）+ L2 单 IP 详情（身份档案+4 Tab）。
**首屏排序**：入口型组件（列表/按钮）必须排在洞察型图表（KPI/分布图）前面——L1 主体列表曾因排后面首屏不可见被误判"页面没有列表"。

### 4.8 F2.1 L2 复合查询的口径

LLM 只选模板填参数，**不生成 SQL**。模板清单在 `configs/query_templates.yaml`（4 模板），执行器在 `app/services/query_templates.py`。参数经类型/范围/枚举校验 + 维度二层白名单。
**统计类模板必须返回 coverage**（如 `{total:73, counted:24, missing:49}`）。
**L1 stats 委托给 L2**——同一实现，别让两条路给不同口径。

### 4.9 采集器两个埋雷（已修）

1. **tplink `__main__.py` `--test` 分支连开 3 个 asyncio.run**——RuntimeError: Event loop is closed。修：三个分支各收敛为单次 `asyncio.run`，收尾同循环内做。
2. **wazuh `yaml.safe_load` 不展开 `${VAR}`**——把字面量 `${WAZUH_PASSWORD}` 当值认证 → 401。修：`collector_framework.config.resolve()`：env 优先 → YAML → default；占位符无 default 抛 ValueError。

### 4.10 后端冷启动 8s+

`main.py` lifespan 注册 N 个 scheduler（graph watchdog + CISA KEV + push + alert digest + scan + ...）。验证脚本要么 `sleep 10+`，要么轮询 `/health` 200。**不要 sleep 5 就开测**——会全 503。

### 4.11 业务系统 owner 字段名占用

`Asset` 模型原 `owner_id` (FK) + `owner` (relationship)，加自由文本责任人时 `owner` 被 relationship 占用 → 改名 `owner_user` 腾名（与 asset 表 `owner` 文本列 + `owner_user` relationship 模式统一）。**新增文本列前先 grep relationship 占用**。

### 4.12 useTable 适配两个坑

1. 分页字段映射：`core.paginationKey = { current: 'page', size: 'page_size' }` 对齐后端
2. 响应提取：`sizeFields` 默认不含 `page_size` → 在 `transform.responseAdapter` 显式解包

### 4.13 同步采集器 `sync_client` 的假绿（**已知未修**）

`sync_client` 把 `body.code=400` 当成同步成功——wazuh/baseline 数据其实没进库，`soc_source_health` 也跟着记 success。**未修原因**：改对会让 `/data-health` 转 degraded——这是正确行为，但要决策是补后端 `data/sync` 类型支持还是接受降级面板。

### 4.14 Mac 到 GitHub 慢网

现象：TCP 能连、发出本地版本串后即断，**不是** key 问题。应急 HTTPS `git push https://github.com/xiejava1018/AI-miniSOC.git master`（已存 `credential.helper=store`）。Bundle 备用：`git bundle create /tmp/full.bundle master` + 服务器 `git fetch`。

### 4.15 102 部署脚本前端构建竞态

`npm ci` 会清 node_modules，紧接着 build 在 8GB 主机上偶发三种假错（SASS `@use 'config'` / `ERR_MODULE_NOT_FOUND` / rollup externalized）。**手动跑 `npx vite build` 全成功**。判定为竞态，`deploy.sh` 改成"lock 变了才 npm ci"（2026-09-12 ee3871a）。**注意**：修改 deploy.sh 的那次部署跑的还是旧脚本，需跑两次。

### 4.16 登录验证码可绕过（**未修安全洞**）

POST `/auth/login` 不带 `captcha_key`/`captcha_code` 即跳过验证。前端表单必填挡了个寂寞。建议后端对启用配置强制校验。

---

## 5. Session 笔记归档

**新 session 笔记不再 append 到本文件**——按主题归档。

- 索引：[`docs/sessions/INDEX.md`](docs/sessions/INDEX.md)（按主题分 14 类，共 33 条历史笔记的定位）
- 原文存档：[`docs/sessions/CLAUDE-archive-v2.36-2026-09-15.md`](docs/sessions/CLAUDE-archive-v2.36-2026-09-15.md)（v2.36 重构前的完整 CLAUDE.md，148KB / 2359 行）
- **新增笔记写法**：写到 `docs/sessions/YYYY-MM-DD-topic.md`，在 INDEX.md 加一行
- **按需加载**：本文件不复制内容，只在 §4 摘要关键教训；要看完整上下文 `Read(archive, offset=行号, limit=N)`

---

## 6. 一些全局约定（项目级）

- **分支**：实际只用 master（无 develop/main），所有 commit 直接 push master
- **emoji 提交**：项目习惯用 ✨🐛📝🔧（CLAUDE.md 注释说不用，但实际很常见）
- **响应包装**：CLAUDE.md 老版本写的 `code=200=成功, 401/4xx=错误` **正确**；`code=0=成功` 是注释文档错误（见 §1.1 + 第 §0 节"硬事实"）
- **审计**：所有写操作默认走 `@log_audit` 装饰器，自动落 hash 链
- **凭证管理**：`.env` 不入库，`.env.example` 是模板；Wazuh/OpenSearch/Loki **当前**走 `soc_data_sources` 表（配置中心 v1 上线后）

---

## 7. 已知未修 / 待办（不阻塞，按需）

详见 [`docs/sessions/CLAUDE-archive-v2.36-2026-09-15.md`](docs/sessions/CLAUDE-archive-v2.36-2026-09-15.md) 各章节「待办（不阻塞）」节，摘要：

- 登录验证码后端强制校验（§4.16 安全洞）
- 同步采集器 `sync_client` 不看 `body.code`（§4.13 假绿）
- Loki 192.168.0.30:3100 不可达（`browsing_detector` 持续降级）
- F2.1 L2 降级文案说"已达调用限额"实际可能是熔断（措辞略偏）
- 旧远端生产库 `111.228.57.2:25432` 暂未删（迁回滚素材）
- 102 本机 PG 没有备份机制
- F1.1 评分权重校准（端口覆盖率 >80% 或接入第二台 Wazuh agent 才触发）
- 采集器 `run_daemon.py` 守护逻辑与 docker restart 重叠
- 业务系统归一化字段（description/criticality）批量回填

---

**版本**: v3.0（2026-09-15 重构）
**重构理由**: 原 v2.36（2359 行）每次加载信噪比极低，过期事实不可枚举。重构后约 350 行，所有硬事实由 `sync_claude_md_truth.py` 同步，session 笔记按主题归档。
**后续维护**: 改 CLAUDE.md 前先问"这服务什么未来决策"。无决策的内容删 / 归档 / 写脚本，不进主文件。
