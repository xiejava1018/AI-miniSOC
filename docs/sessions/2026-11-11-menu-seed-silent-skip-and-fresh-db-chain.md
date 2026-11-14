# 2026-11-11 菜单种子静默跳过 + 空库 upgrade 断链根治

> 事故：生产库（102 / AI-miniSOC-db）「图谱性能看板」「归属确认」「整改工单」三个子菜单缺失，
> 但 alembic_version 与 dev 完全一致（都是 head）。排查发现**两处独立的迁移链完整性缺陷**。
> commit：`9c62dfe`；生产即时修复：幂等 SQL + 行数断言。

## 现象与判断要点

| 对象 | 生产库 | dev 库 |
|---|---|---|
| soc_graph_perf_alerts / soc_attribution_reviews / soc_remediation_tickets 表 | ✅ 存在 | ✅ |
| 对应三个菜单 | ❌ **全缺** | ✅ |

「表建了、菜单没有」——建表 DDL 跑了、同文件里的菜单 INSERT 没跑。两者唯一的分叉是
**`INSERT ... SELECT` 在源查询为空时静默插入 0 行且不报错**（CLAUDE.md §4.3 红线 2 的又一实例）。

## 根因 1：菜单种子迁移在生产库从未执行

三个种子迁移（`b6c7d8e9f0a1` / `e9f0a1b2c3d4` / `g3b4c5d6e7f8`）的插入模式：

```sql
INSERT INTO soc_menus (...)
SELECT p.id, '整改工单', ...
FROM soc_menus p WHERE p.path = '/assets' AND p.parent_id IS NULL
  AND NOT EXISTS (...)
```

生产库的 schema 是手工建的，随后 `alembic stamp head` 一次性标记全部迁移已应用。
**stamp 不执行任何迁移体** → 这三个 INSERT 从未在生产库跑过。
表能存在是因为后续其他迁移用 `CREATE TABLE IF NOT EXISTS` 补建了（又一次"老库掩盖链缺陷"）。

`created_at` 时间戳是铁证：102 上 10/6 前后的菜单都在，唯独 10/3–10/5 三个窗口缺失。

## 根因 2：空库 `upgrade head` 在第 73 步断链（顺手挖出的更深问题）

按 §4.3 红线 6 在真·空库验证，失败：

```
column "linked_asset_id" referenced in foreign key constraint does not exist
```

`soc_alert_group_analyses` 由 `e2f3a4b5c6d7` 用裸 SQL `CREATE TABLE IF NOT EXISTS` 建立，
只有 9 列、**不含 linked_asset_id**，且多出 verdict_at/ai_model/explanation 三个 ORM 里没有的列。
带 `IF NOT EXISTS` 后：
- 老库：表已被 `create_all()` 按 ORM 建好 → CREATE 被跳过 → 正常
- 空库：CREATE 生效 → 列集缺列 → `e3f4a5b6c7d8` 重建 FK 时炸 → 整条链断

## 修复

### 生产即时修复（幂等 SQL + 断言）

单事务内：父菜单存在性校验 → 三个 INSERT（NOT EXISTS 守卫）→ 断言菜单就位 →
12 条角色授权（3 菜单 × 4 X1 角色）→ 断言授权齐全。任一断言失败即 ROLLBACK。
备份：`/tmp/menus_backup_20261110.sql`。

### 根治迁移（commit 9c62dfe，两个新迁移）

1. `m1n2o3p4q5r7_menu_backfill_with_assertions.py`：
   - 15 个 /assets 子菜单作为**显式清单**重新播种（幂等）
   - 每步断言行数：插入 0 行且菜单不存在 → `raise RuntimeError`（静默 0 行 → 响亮失败）
   - 终态断言：3 菜单 × 4 角色授权齐全
2. `n2o3p4q5r6s7_fix_alert_group_analyses_columns.py`：列集补齐到 ORM 的 17 列
3. 修改 `e3f4a5b6c7d8`：建 FK 前先 `ADD COLUMN IF NOT EXISTS`（该迁移在所有已部署库
   早已跑过，改动只影响空库）
4. 回归测试 ×3（`test_fresh_install_bootstrap.py`）：子菜单存在性、X1 授权完整性、
   **静态检查根治迁移必须带行数断言**（防后人删断言）

## 验证

- 真·空库 `upgrade head`：EXIT=1 → **EXIT=0**，85 表 / 15 个 /assets 子菜单 / 60 条授权 / 17 列齐全
- 幂等：downgrade -1 → 12 个 → upgrade → 15 个，循环通过
- 断言有效性：删父菜单后 `_assert_parent_menu` 正确 raise，事务回滚

## 澄清两个误判（记录以防再犯）

1. **「alembic 有未合并分支」是误判**。`alembic branches` 报的 `z6a7b8c9d0e1` branchpoint
   是**已 merge 的菱形结构**——merge 节点 `628109e83308` 的 down_revision 是
   tuple `("r4s5t6u7v8w9","v7w8x9y0z1a2")`。用 `ScriptDirectory` 权威判定：
   **99 个迁移全部在 head 祖先集，单 head 单 base**。
2. **「13 个孤儿迁移」也是误判**——是 `--sql` 输出截断 + awk 解析错位的假象。

**教训：判断迁移链结构，用 `alembic heads` + `ScriptDirectory.iterate_revisions`，
不要自己 grep + awk 解析文本输出。**

## 附带发现（本次未修）

- 测试 `test_default_admin_can_authenticate` / `test_menu_tree_is_complete_and_admin_has_full_access`
  是**既有失败**（admin 缺 /reports /ops 顶级菜单授权；密码常量与 .env 不一致）
- `alembic check` 持续报模型/迁移不一致（大量 remove_table/modify_comment 噪音）——
  涉及 soc_remediation_tickets / soc_attribution_reviews 等"ORM 有、迁移链没建"同类问题，待专项清理
