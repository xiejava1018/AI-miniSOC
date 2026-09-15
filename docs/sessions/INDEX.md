# Session 笔记主题索引

> 来源：`docs/sessions/CLAUDE-archive-v2.36-2026-09-15.md`
> 创建日期：2026-09-15（CLAUDE.md 重构时同步建索引）
> 索引规则：按主题分类，不复制原文；定位用「行号区间」精确指向原文
>
> 怎么用：在新 CLAUDE.md 里只看到主题名 → 想细查时 `Read(archived, offset=行号, limit=N)`

---

## 主题速查

| 主题 | 条数 | 主要内容 |
|---|---|---|
| [CI/CD 与部署](#cicd-与部署) | 2 | 自动化部署、采集器 CD 缺口、102 服务器、迁移 |
| [权限矩阵 X1](#权限矩阵-x1) | 4 | require_role/require_button_permission、菜单树粒度 bug、全菜单授权 |
| [alembic / 数据库迁移](#alembic--数据库迁移) | 2 | 空库 upgrade 跑通、多 head 修复、JSONB 写法 |
| [菜单 / UI / icon](#菜单--ui--icon) | 7 | /ops 容器、iconify ri:* 严格、稽核/对账文案、菜单重排 |
| [资产知识图谱](#资产知识图谱) | 1 | IdentityGraphBuilder 阻塞根治、asyncio.to_thread + threading.Lock |
| [行为画像 / 上网行为](#行为画像--上网行为) | 3 | 两层结构、L1 主体列表首屏、入口跳转 |
| [资产扫描 / scanner](#资产扫描--scanner) | 1 | Phase 1+2 全量落地、ScanFinding UUID、X-API-Key 鉴权 |
| [AI / LLM / F2.x](#ai--llm--f2x) | 4 | L2 复合查询、变更影响分析、报告生成、W0 评测集 |
| [配置中心](#配置中心) | 3 | 数据源走 DB、配置审计合并、过期文档评审 |
| [业务系统管理](#业务系统管理) | 4 | F9 CRUD、菜单、对齐角色页、负责人/部门/电话 |
| [资产字段 / 数据模型](#资产字段--数据模型) | 2 | network_zone 5→8 值改造、merge 双 head、字典 seed + backfill 脚本、生产 alembic 落后事故救援 |
| [告警分级 / 风险评分](#告警分级--风险评分) | 3 | alert_levels 全项目唯一、Top 10 D7 vs F1.1 口径澄清、rising 修复 |
| [数据补齐地基 P0](#数据补齐地基-p0) | 1 | F9/F10/F11、parent_id 模型对齐、后端冷启动 8s+ |
| [采集器 / 僵尸进程 / 凭证](#采集器--僵尸进程--凭证) | 1 | tplink asyncio.run 循环错位、wazuh yaml 不展开 ${VAR} |
| [生产库迁移](#生产库迁移) | 1 | 102 本机 PG、49 表逐表 count 比对、回滚素材 |
| [早期 session 笔记](#早期-session-笔记) | 1 | 2026-06-07 早期 Python 升级、采集器架构等 |

---

## CI/CD 与部署

- **2026-08-19 CI/CD 上线** (L587–615) — push master → CI 三绿 → self-hosted runner `aisoc-prod-deployer` 自动部署 192.168.0.102，失败全局 trap 回滚；`deploy.sh` 含 fetch depth+timeout/pip/vite build/systemd restart/双探活
- **2026-08-23 采集器 unhealthy / 僵尸进程 → CI/CD 缺口** (L1344–1480) — `src/collectors/` 完全在 CI/CD 之外的发现与修复；`deploy_collectors.sh` 补上；wazuh `yaml.safe_load` 不展开 `${VAR}` bug + 修复

## 权限矩阵 X1

- **2026-08-22 P3/X1 权限矩阵** (L704–761) — admin/operator/viewer/auditor 4 角色；`require_role()` + `require_button_permission()`；4 写操作端点接权限；EOL 覆盖走 admin+operator
- **2026-08-22 续二：X1 权限矩阵收尾** (L967–994) — **真安全洞**：`get_menu_tree` 原"父菜单授权 → 全子菜单放行"逻辑；合规两个写端点、审计日志端点补权限；全菜单授权回填
- **2026-09-12 续：配置审计合并到审计日志** (L1853–1913) — `ConfigAuditService` 转调 `AuditLogService.create_audit_log()` 进 hash 链；删 ConfigChangeLog 模型 + 4 文件 + 1 页面

## alembic / 数据库迁移

- **2026-08-22 续三：todo#4 空库 alembic 跑通 → P3 收官** (L995–1024) — 新迁移 `ab9cd0e1f2a3` 幂等补齐 7 张手工表 + 7 个手工列；空库 upgrade head（27 步 48 表）→ downgrade base → 再 upgrade 干净
- **2026-09-14：P0 数据补齐地基落地 — F9/F10/F11** (L2053–2162) — F11 Asset.parent_id 模型对齐 DB；F9 业务系统 CRUD API；F10 AssetUpdate 拓归属字段

## 菜单 / UI / icon

- **2026-08-22 续四：菜单重组 /ops 运维管理** (L1025–1060) — 新顶级 /ops；移动 4 子菜单；资产对账→资产稽核（不改 button authMark）
- **2026-08-22 续五：菜单顺序重排 + title/icon 补全** (L1061–1101) — 9 顶级菜单按用户指定顺序；HTML entity 当 icon 不渲染的坑
- **2026-08-22 续六：资产稽核/安全报告 icon 修正 + 页面文案统一** (L1102–1142) — 'ri:git-compare-line' 不存在 → 'ri:scales-3-line'；'Document' Material 字符串 → 'ri:file-shield-2-line'；前端文案对账→稽核 7 个文件
- **2026-09-06 续二：L1 主体列表首屏不可见修复** (L1771–1804) — 行为画像入口型组件必须排在洞察型图表前面；CDP 实测 146 快照/73 IP；登录验证码可绕过洞
- **2026-09-14：业务系统管理页重构 — 整体对齐角色管理页** (L2229–2279) — 业务系统页必须套 `useTable` + `ArtTable`，不能用裸 ElTable；分页字段映射 + 响应提取两个 useTable 适配坑
- **2026-09-14：业务系统 v1.1 — 责任人自由文本+电话+部门下拉** (L2280–2326) — `owner` 字段名被 relationship 占用 → 改名 `owner_user` 腾名；create 端点漏传新字段 bug
- **2026-09-14：业务系统部门下拉空的修复 — page_size 超限 422** (L2327–2358) — 前端 page_size=200 > 后端 Query(le=100) 上限被 422 拒，envelope 包成 200 + data=None → 静默空数组

## 资产知识图谱

- **2026-09-14：资产知识图谱 graph builder 阻塞根治** (L1971–2052) — IdentityGraphBuilder 同步跑在 event loop 拖死全站；`_run_builder_in_thread()` + `threading.Lock`（不用 asyncio 锁）；`_now` 重复关键字参数必崩 bug

## 行为画像 / 上网行为

- **2026-09-06：行为画像全量落地 + 入口跳转** (L1644–1735) — 9 commit 速查；§9 验收核对；S6 traffic_type 自动判定修复（`compute_traffic_type` 加双辅助判据）
- **2026-09-06 续：行为画像两层结构改造实施** (L1736–1770) — L1 群体概览 + L2 单 IP 详情；D2 关系 Tab ECharts graph 力导向拓扑；方案 S1-S7 全落地
- （L1 首屏不可见见"菜单 / UI / icon"）

## 资产扫描 / scanner

- **2026-08-26：P3+ 资产发现与攻击面扫描采集器 Phase 1+2** (L1535–1643) — 4 张表 + 15 个新端点；**`ScanTask` 类名被 vulnerability.py 占用 → 用 `ScannerTask`**；`ScanFinding.matched_asset_id` 类型必须是 UUID；alembic 迁移三连坑（op.execute 双参数/:perms::jsonb/soc_role_menus 无 created_at）

## AI / LLM / F2.x

- **2026-08-21 P3/F2.2 上线** (L644–675) — 安全报告；router prefix 与 endpoint 路径不要双重前缀；GLM prompt 不要同时说"输出 JSON"和"用列表"
- **2026-08-22 P3/F2.1 L2 复合查询 + 告警计数假阴性修复** (L816–901) — **真安全教训**：把 99 条 critical 报成 0 比查询失败更危险；计数类需求一律用服务端聚合，不要取 N 条文档客户端数
- **2026-08-22 P3/F3.1 变更影响分析** (L762–815) — 关键词提取零 LLM 成本 → 资产定位 → 粗粒度关联 → OpenSearch → GLM；honest 降级；target_count 膨胀 bug
- **2026-08-22 续：W0 评测集 + LLM-SQL 路径审计** (L902–966) — 50 条评测集基线 49/50=98%；**Go/No-Go 安全项审计通过**：项目无 LLM 生成 SQL 路径（全是 select() 构造体）

## 配置中心

- **2026-09-11：配置中心设计文档评审修订 + CLAUDE.md 过期记载清理** (L1805–1852) — 推翻 D5「不走 Alembic」前提错误；§6.5 菜单 SQL 6 处错误重写；约定 C11/C12
- **2026-09-12：配置中心 v1 上线 + Wazuh/OpenSearch 走 DB** (L1914–1970) — 本地 testdb 补 migrate；生产 102 手动 git reset + migrate；3a 写 3 个数据源到 soc_data_sources；3b .env 数据源键标记废弃；3c 11 个后端调用点迁移到 resolver

## 业务系统管理

（见"菜单 / UI / icon"中的 4 条业务系统记录）

## 资产字段 / 数据模型

- **2026-XX-XX：network_zone 5→8 值改造** — 公网/DMZ/生产/办公/开发/管理网/隔离区/未分类；alembic merge 双 head（628109e83308）；字典 seed 8 值 + 历史 intranet/other 合并；backfill 脚本 5 条高置信度二次回填规则；`other` 不可信统一 `unknown`；云服务器按角色选（SLB=public/ECS=dmz or production/蜜罐=isolated/堡垒机=management）
- **2026-XX-XX：生产 alembic 落后事故救援** — 生产 500 + 业务系统菜单缺失；生产 alembic_version 停 k6l7m8n9o0p1 落后 7 迁移；原因是 deploy.sh 只跑 alembic check 不跑 upgrade；修复：手动 upgrade head 7 迁移 + 字典 seed + deploy.sh 改为自动 upgrade + 双保险验证

## 告警分级 / 风险评分

- **2026-08-22：Top 10 高危资产「评分」口径澄清** (L1209–1244) — Top 10 卡片"评分"是 D7 加权和（200+），**不是** F1.1 风险评分（0–100）；前端卡片副标题 + tooltip 标注口径
- **2026-08-22：评分上升最快 rising 修复** (L1245–1295) — rising 改"次新快照"基线；阈值 `>=10 → >=5`；列名 `delta_7d → delta`
- **2026-08-22：rising v2 修正「次新基线」语义不达生产预期** (L1296–1343) — **v2.20 仍空，根因是生产数据跟本地 testdb 不一致**；改"最早一条 history 快照"基线；教训：CLAUDE.md 里"数据都一样"是伪命题

## 数据补齐地基 P0

- **2026-09-14：P0 数据补齐地基落地 — F9/F10/F11** (L2053–2162) — alembic check 噪音 ≠ 真问题；art-design-pro-edge 是后端驱动菜单；audit_decorator lambda 签名；business_system_names 加载防 N+1；后端冷启动 8s+

## 采集器 / 僵尸进程 / 凭证

- **2026-08-23：采集器 unhealthy / 僵尸进程 → CI/CD 缺口** (L1344–1480) — tplink `__main__.py` 的 `--test` 分支连开 3 个 asyncio.run 导致 RuntimeError；`TPLinkCollector` 补 close()；compose `init: true`；wazuh `yaml.safe_load` 不展开 `${VAR}` → 401

## 生产库迁移

- **2026-08-23 续八：生产库从远端迁到 102 本机** (L1481–1534) — 远端 `111.228.57.2:25432` → 102 本机 `192.168.0.102:5432`；逐表精确 count 比对（49/49 全等）；回滚素材在 /tmp/aisoc-db-migrate-20260823-021834/

## 早期 session 笔记

- **2026-06-07 session 续记** (L562–586) — Python 升级 3.9.6→3.13.2；采集器架构 src/collectors/；数据同步 data_sync；24 张表

---

## 归档原则（重要）

1. **保留原文**：本索引不复制内容，只给定位。所有原文都在 `CLAUDE-archive-v2.36-2026-09-15.md`
2. **行号定位**：`Read(CLAUDE-archive..., offset=行号, limit=N)` 直接打开对应小节
3. **不删除**：归档而非删除，未来查"为什么当初这么设计"时仍然有价值
4. **新增 session 笔记不再 append**：以后每次完成工作，写到 `docs/sessions/YYYY-MM-DD-topic.md`，本索引同步加一行
