# 2026-10-06：admin 角色菜单授权补齐（dev testdb）

> 主题：菜单权限 / alembic / 三库隔离
> 关联：CLAUDE.md §1.3 菜单树粒度、§4.3 迁移红线、§1.7 三库分离、§5 笔记归档

## 现象

http://localhost:5173/（dev testdb）admin 登录后看不到「配置中心」顶级菜单，
资产管理下也缺「资产图谱」「图谱性能看板」。CLAUDE.md §0 硬事实说顶级 11 个，
dev testdb 实测只有 10 个，差的正好是配置中心。

用户提问路径：
1. 「为什么菜单不见了？」—— 查 admin 的 `soc_role_menus`
2. 「权限是怎么丢的？」—— 查 alembic 迁移历史
3. 「以前 102 和 5173 是一样的？」—— 跨环境对比
4. 「菜单 ID 怎么不一致？」—— 三库独立性

## 根因（三层叠加）

### 1. `d2e3f4g5h6i7_config_center_v1.py`（CLAUDE.md §4.3 红线 2 静默 0 行）

按当时 init_system_data.py 写入的「系统管理」行 path = ''，但迁移脚本里写
`WHERE path = '/system' AND parent_id IS NULL` —— 父菜单解析不到，CROSS JOIN
产出空集合，`INSERT ... SELECT` 静默 0 行，alembic upgrade 仍返回成功。
后续 `e2f3g4h5i6j7_fix_config_center_menu_seed.py` 修了 path 后种菜单行 +
补 admin 授权，但 dev testdb 上 admin 的 `soc_role_menus` 仍然没有
id=62/64/68 的记录（说明补授权那段的 `NOT EXISTS` 守卫当时认为 dev 上
admin 已有授权 —— 实际是另一条子菜单重复 SELECT 出错）。

### 2. `i4j5k6l7m8n9_reorganize_config_menus.py`（2026-09-13 commit 7c793d3）

新建顶级 /config (id=71) 容器，把 3 子菜单从 /system 移到 /config 下。
**只改 `soc_menus.parent_id`，完全没碰 `soc_role_menus`**。

MenuService.get_menu_tree 算法：
```python
parent_ids = {m.parent_id for m in all_menus
              if m.parent_id is not None and m.id in assigned_ids}
menus = [m for m in all_menus if m.id in assigned_ids or m.id in parent_ids]
```

dev testdb 上 admin 从未获得 62/64/68 授权 → `parent_ids = ∅` → 71 顶级
不满足①自身被授权，也不满足②作为容器 → 整个 /config 消失。

### 3. `t3u4v5w6x7y8_asset_knowledge_graph_v1.py` + `b6c7d8e9f0a1_graph_perf_dashboard_menu.py`

asset graph v1 在 admin role_menus 给 id=72(资产图谱) 加了
`["view","rebuild","export"]`；graph perf 加了 id=77(图谱性能看板)
`["view","reset"]`。但 dev testdb 上 admin 实际没有这两项。

**生产 102 上 admin 是有的**（SSH 实测）—— 说明这两条迁移的生产 DB 跑过授权 SQL
成功；但 dev testdb 上的 admin 那行 INSERT 没生效（同 §4.13 sync_client 假绿
坑，silent 0 row 模式 + NOT EXISTS 守卫短路）。

## 三库隔离的本质

dev testdb / 生产 102 / pytest 三个 DB 是**完全独立**的实体，BigSerial 主键
`SERIAL` 重置 → 同样的 `INSERT` 在不同 DB 产生不同 id（102 上配置中心顶级 = 74，
dev 上 = 71）。CLAUDE.md §1.7 明确禁止本地 .env 指向生产库，但**两库迁移
进度差异是历史遗留下来的**：

| 库 | alembic head | 与 102 差异 |
|---|---|---|
| dev testdb | i5d6e7f8a9b0 (现在 j6a7b8c9d0e1) | dev **领先** 6 条（9-13 后工作） |
| 生产 102 | 4d5e6f7a8b9c | 缺 6 条 OH-UI.10+ 工作 |

BigSerial 的特性 + 不同步的迁移历史 → ID 永远对不上，**菜单 ID 一致不是预期**。
CLAUDE.md §0 硬事实「顶级菜单 11 个」是**生产 102 的实测数**。

## 修复（A 路径）

新 alembic 迁移 `j6a7b8c9d0e1_admin_menu_backfill.py`：

```python
INSERT INTO soc_role_menus (role_id, menu_id, permissions)
SELECT r.id, m.id,
       CASE WHEN m.path = '/config' AND m.parent_id IS NULL
            THEN NULL  -- 容器菜单
            ELSE CAST((SELECT jsonb_agg(e->>'authMark')
                       FROM jsonb_array_elements(m.permissions) e) AS jsonb)
       END
FROM soc_roles r CROSS JOIN soc_menus m
WHERE r.code = 'admin'
  AND ((m.path = '/config' AND m.parent_id IS NULL)
    OR (m.path IN ('config-center','data-source','ai-provider') AND m.parent_id IS NOT NULL)
    OR (m.path = 'graph' AND m.parent_id IS NOT NULL)
    OR (m.path = 'graph/perf-dashboard' AND m.parent_id IS NOT NULL))
  AND NOT EXISTS (...)
```

设计约束（CLAUDE.md §4.3 红线全中）：
- JOIN 子查询定位 admin role / 菜单，**不硬编码 id**
- WHERE 用 path（CLAUDE.md §4.3 教训：path 是不变式，name/title 历史混用过）
- NOT EXISTS 守卫幂等
- 容器菜单 id=71 给 NULL perms（CLAUDE.md §1.3 算法②会从子菜单 parent_id
  反推父容器，但显式授权更清晰、不依赖服务层推断）
- JSONB 用 CAST(... AS jsonb)（CLAUDE.md §4.3 红线 4：`:perms::jsonb` 当绑定参数）
- downgrade 镜像撤销（只删本迁移新增 6 项）

### 验证（CLAUDE.md §4.3 教训「执行后必须回读确认」）

| 项 | 验证前 | 验证后 |
|---|---|---|
| alembic head | i5d6e7f8a9b0 | j6a7b8c9d0e1 |
| admin role_menus 总数 | 44 | 50 (+6) |
| 顶级菜单数（admin） | 10 | **11**（CLAUDE.md §0 对齐）|
| 资产管理子菜单 | 7 | 9 (+72 资产图谱 +77 图谱性能看板) |
| 二次跑 NOT EXISTS | — | 0 行（幂等）|
| Rollback 后状态 | 44 | 44（零污染）|

## 留待 B 路径

dev testdb 应该追到与生产 102 同步的 head + 之后 dev 多出的 6 条。但因：

- Mac 到 111.228.57.2 远端 testdb 是慢网（CLAUDE.md §4.14）
- dev .env 现在指远端 testdb，理想环境是本地 PG 专库
- B 价值是长期维护性，不阻塞当前 dev 工作

→ **A 已完成，B 排期不阻塞**。

## 防回归建议（CLAUDE.md §0 同步脚本增强）

`sync_claude_md_truth.py` 当前只读菜单表行数（11 ✅），不读 admin 实际可见
菜单数（dev 修复前是 10）。增强为 invariant 检查：admin 顶级可见菜单数
应该 = 菜单表顶级总数，dev 端缺授权会被立刻报警。

## 关联 CLAUDE.md 章节

- §1.3 菜单树粒度（子菜单须自身被授权）
- §1.7 三库严格分离
- §4.3 迁移 4 条红线（dry-run / 禁硬编码 id / bind.execute / CAST jsonb）
- §4.13 sync_client 假绿（同款 INSERT 静默 0 行）
- §5 session 笔记归档
- §0 硬事实快照