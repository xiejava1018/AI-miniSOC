# 2026-XX-XX 生产 alembic 落后事故救援（102 后端 500）

## 事故现象

生产 192.168.0.102:8080 多页面报 500：

- **资产管理-业务系统**菜单缺失（前端没有该菜单）
- **资产列表**报 `Request failed with status code 500`
- 后端日志：`UndefinedColumn: column soc_assets.business_impact does not exist`、`UndefinedColumn: column soc_assets.public_ip does not exist`、`UndefinedColumn: column soc_scanner_tasks.affected_ports does not exist`

## 根因

**CI/CD 部署流程从未自动跑 alembic upgrade**。

- `deploy.sh` 第 176 行：`./venv/bin/alembic check` 故意只检查不升级（"非阻塞告警"）
- `deploy.sh` 第 258-266 行：检查 `alembic current != heads` 也只 log WARN，**不动手**
- 生产 DB 的 `alembic_version` 停在 `k6l7m8n9o0p1`，落后 master 5 个迁移（实际 7 个，包括 z6a7b8c9d0e1 → q9r8s7t6u5v4 这一段）
- 代码用新 schema（三维度、公网 IP、scanner affected_ports），DB 没有对应列

## 未跑的迁移清单（按顺序）

```
k6l7m8n9o0p1 (生产当前，2026-09-13)
  ↓
t3u4v5w6x7y8  资产知识图谱 v1（节点/边表 + 业务系统 + 账号→人映射）
  ↓
u5v6w7x8y9z0  业务系统管理菜单（v1 §7.0 WO-0a / §7.2.5 F9）
  ↓
v7w8x9y0z1a2  业务系统责任人改自由文本 + 联系电话
  ↓
z6a7b8c9d0e1  browsing 父菜单 component 修复（之前未观察到的分支）
  ↓
q9r8s7t6u5v4  资产/业务系统重要性三维度改造（business_impact / data_sensitivity / protection_level）
  ↓
p3q4r5s6t7u8  业务系统菜单移到 /assets 下
  ↓
r4s5t6u7v8w9  修复字典表 is_default NULL
  ↓
628109e83308  network_zone 8 值改造（本次新迁移）
```

## 救援步骤（实际执行）

### 1. 确认状态
- `alembic_version = k6l7m8n9o0p1`（生产当前）
- `alembic heads = 628109e83308`（master 当前，mergepoint）
- 部分表手工建过（`soc_graph_nodes`、`soc_asset_business` 等存在）但 schema 中很多列缺失
- 后端报错日志确认具体缺哪些列

### 2. 停后端
```bash
systemctl stop aisoc-backend
pkill -9 -f uvicorn  # 清残留
```

### 3. alembic upgrade head
```bash
cd /home/xiejava/AIproject/AI-miniSOC/src/backend
./venv/bin/alembic upgrade head
```
输出 7 个迁移全部成功。

### 4. 字典 seed（8 值）
```bash
./venv/bin/python scripts/init_system_data.py  # 或只跑 init_dicts
```
- 合并 intranet→production、other→unknown
- 新增 public、dev、isolated
- 排序 sort_order 为 1-8 连续

### 5. 修 management sort=5→6
（`init_system_data.py` 里 `_migrate_network_zone_dict` 的 `_sort_orders` 曾把 management 写错为 5，与 dict_items 里的 dev=5 冲突）

### 6. 后端自动重启
（systemd Restart=always 自动拉起，无需手动 start）

### 7. 验证
- `/health` 200
- `/api/v1/assets/?limit=2` 200，返回 76 行（原数据完整）
- 三维度列 `business_impact/data_sensitivity/protection_level` 全部存在
- `network_zone` CHECK 8 值生效，数据映射完成（73 production + 3 unknown）
- `soc_dicts.network_zone` 8 行，sort 1-8 连续
- 业务系统菜单 `name=business-system`、`title=业务系统`、component 指向 `/asset/business-system/index`

## 永久修复（deploy.sh）

修改 `deploy/deploy.sh`：

1. **Step 5**（后端 deps 后、前端 build 前）：
   - 自动 `./venv/bin/alembic upgrade head`
   - 失败 `exit 5` 触发 trap 回滚（避免代码上新 schema 落后）
   - 位置关键：deps 后保证 alembic CLI 已装；build 前保证即使 build 失败 DB 也已一致

2. **Step 10**（health check 后）：
   - 验证 `alembic current == alembic heads`
   - 不一致 `exit 6` 触发 trap 回滚（双保险）

3. 保留 `alembic check` 为**诊断信息**（非阻塞）

## 与 CLAUDE.md 老版本"alembic 是 2 个 head"的关系

CLAUDE.md §0 表格说"alembic 2 个 head（r4s5t6u7v8w9, v7w8x9y0z1a2）"是**正确**的 —— 但本次事故的根因**不是**双 head，而是 **CI/CD 从未自动跑 upgrade**。

`628109e83308` 是**合并双 head** 的迁移，所以升级后 head 数从 2 → 1。CLAUDE.md 已同步更新（"1 个 head 628109e83308"）。

## 给 DBA / 运维的 checklist

下次部署前（或收到 alembic 落后告警时）：

1. `cd /home/xiejava/AIproject/AI-miniSOC/src/backend`
2. `./venv/bin/alembic current` —— 看生产版本
3. `./venv/bin/alembic heads` —— 看代码期望版本
4. 不一致 → `./venv/bin/alembic upgrade head`（自动跑了，可跳过；这次事故前是手工跑）
5. 如果 `alembic upgrade head` 报错 → 查看错误信息，必要时 `./venv/bin/alembic downgrade -1` 回滚最后一个迁移

## 后续注意

- 以后所有 schema 变更都要走 alembic 迁移，**禁止手工 DDL**（CLAUDE.md §4.3 已有教训）
- 如果确实需要手工建表（如 2026-08-22 那次），必须**同时写一个迁移文件** + **手动更新 alembic_version 表**
- CI/CD 现在自动跑 upgrade，无需手工干预；如果 upgrade 失败，CD 会回滚并报警