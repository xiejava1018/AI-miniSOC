# 2026-XX-XX network_zone 8 值改造（CLAUDE.md §0 立项）

## 改了什么

`Asset.network_zone` 从 **5 值** (`intranet/dmz/office/management/other`) 改造为 **8 值** (`public/dmz/production/office/dev/management/isolated/unknown`)。

8 值方案的判断逻辑（运维/纳管决策树）：

```
蜜罐/取证?  → isolated
直接面向互联网入口(无前置)? → public
员工办公终端? → office
iLO/iDRAC/堡垒机/带外? → management
开发/测试/Staging? → dev
对外服务前置(Web/API Gateway/VPN)? → dmz
生产业务核心? → production
都不到? → unknown (≠ 'other'，触发人工复核)
```

完整设计与云服务器选型示例见 [`docs/design/network-zone-redesign.md`](../design/network-zone-redesign.md)。

## 改的文件清单（7 个）

### 后端（6 个）

| 文件 | 改动 |
|---|---|
| `src/backend/alembic/versions/628109e83308_network_zone_eight_values.py` | **新文件**：merge 两个 alembic head（`r4s5t6u7v8w9` + `v7w8x9y0z1a2`），DROP→UPDATE→ADD CHECK 替换（顺序见踩坑）+ 列 COMMENT 更新；`down_revision = ('r4s5t6u7v8w9', 'v7w8x9y0z1a2')` |
| `src/backend/scripts/init_system_data.py` | 字典 seed 8 值；`_migrate_network_zone_dict()` 把旧 intranet/other 行就地合并到 production/unknown；for 循环改为原生 SQL `INSERT ... ON CONFLICT DO NOTHING`（绕开 ORM 缓存）|
| `src/backend/scripts/backfill_network_zone.py` | **新文件**：5 条二次回填规则（prod→dev / unknown→public / unknown→isolated / unknown→management / office→prod），幂等 + `--dry-run` + `--skip-dev-rule` + `--include-office-server-rule` 开关；底部 `ROLLBACK_SQL`；`for row, in` → `for row in` 修 Row 解包 bug |
| `src/backend/app/services/sync_handlers/asset_sync_handler.py:195` | 白名单 5→8；非法值收敛 `intranet` → `unknown` |
| `src/backend/app/api/scan_tasks.py:623` | scanner 纳管默认值 `other` → `unknown` |
| `src/backend/app/models/asset.py:34` + `src/backend/app/schemas/asset.py:23` | 默认值 `other` → `unknown`；列 COMMENT 指向设计文档 |

### 前端（1 个）

| 文件 | 改动 |
|---|---|
| `src/frontend/src/views/asset/list/index.vue:899/1067/1091` | formData 默认值 `other` → `unknown`（编辑回填 + add 分支） |

### 文档（2 个新文件）

- `docs/design/network-zone-redesign.md` — 8 值方案完整设计文档
- `docs/sessions/2026-XX-XX-network-zone-redesign.md` — 本笔记

## 关键决策（避免下次重做时重新讨论）

1. **`other` 不可信，统一为 `unknown`**：`other` 是任意填的兜底，新形态资产（云、蜜罐）填到这里 = 分类失效；`unknown` 才是真兜底，会触发人工复核。这是"语义对齐"的核心。
2. **CHECK 替换必须 DROP → UPDATE → ADD 顺序**（见踩坑）：PG CHECK 默认 IMMEDIATE，UPDATE 在老 CHECK 下立即检查，违反新值会被拒。
3. **CHECK 表达式必须显式带引号**：裸 tuple `('public','dmz',...)` 在 PG 里会被当列名/类型名报错，必须用 `', '.join(f"'{v}'" for v in zens)` 拼字符串。
4. **字典 seed 必须先 _migrate 再 for 循环**：for 循环用 `INSERT ... ON CONFLICT DO NOTHING` 原生 SQL（绕开 ORM session 缓存问题，见踩坑）。
5. **`network_zone` 与 `exposure_level` 正交**：前者看"网络位置"，后者看"对外暴露程度"。不要混。
6. **云服务器按角色选，不再按"是不是云"**：SLB=public、ECS=dmz/production(看业务属性)、蜜罐=isolated、堡垒机=management。
7. **二次回填脚本默认保守**：规则 1-4 ON，规则 5（office→production）默认 OFF，避免误判员工机器上的 Linux VM。

## alembic 双 head 处理

CLAUDE.md §0 已警告"2 个 head 风险"。本次新迁移直接 **merge 双 head**（`down_revision = tuple`），不再产生第 3 个 head。未来所有迁移都应在合并后的下游扩展。

**ID 冲突坑**：原本想用 `c1d2e3f4g5h6` 作为 revision ID，但这个 ID 已被 `628109e83308_rename_browsing_menu_and_reorder.py` 占用（2026-09-06）。alembic 加载时报警"Revision present more than once"。**最终改为 `628109e83308`**（全新随机生成）。

## 部署顺序（生产环境）

1. `cd src/backend && alembic upgrade head` —— 跑 `628109e83308` 迁移（数据 + CHECK 替换 + 双 head 合并）
2. `python3 scripts/init_system_data.py`（或只跑 `init_dicts`）—— 字典 seed 8 值 + 历史 dict 行合并
3. `python3 scripts/backfill_network_zone.py --dry-run` —— 预览二次回填影响
4. 人工确认后：`python3 scripts/backfill_network_zone.py` —— 实际回填（prod→dev 等）
5. 前端不需要单独部署，已随 master 一起上线；字典由前端 dictStore 重新拉取生效

## 踩坑教训（重做相关字段时必读）

### 坑 1：CHECK 替换顺序错（最严重）

**错误做法**：UPDATE → DROP CHECK → ADD CHECK
```python
op.execute("UPDATE soc_assets SET network_zone = 'production' WHERE network_zone = 'intranet'")  # ❌ 老 CHECK 还在，立即报 CheckViolation
op.execute("ALTER TABLE soc_assets DROP CONSTRAINT soc_assets_network_zone_check")
op.execute("ALTER TABLE soc_assets ADD CONSTRAINT ... CHECK (network_zone IN ('public',...))")
```

**正确做法**：DROP CHECK → UPDATE → ADD CHECK
```python
op.execute("ALTER TABLE soc_assets DROP CONSTRAINT IF EXISTS soc_assets_network_zone_check")  # ✅ 先解放
op.execute("UPDATE soc_assets SET network_zone = CASE network_zone ... END")  # ✅ 老 CHECK 已不在
op.execute("ALTER TABLE soc_assets ADD CONSTRAINT ... CHECK (...)")  # ✅ 最后加新约束
```

PG CHECK 默认 IMMEDIATE——每行 UPDATE 立即检查，不等事务结束。

### 坑 2：alembic revision ID 冲突

生成新迁移时**必须先检查是否已被占用**：
```bash
cd src/backend && ls alembic/versions/*.py | xargs grep -l "revision: str"
```

或用 alembic 自动生成（`alembic revision -m "..."`），让它给个不会冲突的 ID。

**手工指定的 ID 必须保证 12 位 hex 唯一**。

### 坑 3：ORM session 缓存导致 _migrate 改名丢失

```python
# 错误：用 ORM 改字段 + 后续 ORM 查询看不到新值
old_row.dict_code = "production"  # ORM in-memory 改
db.query(Dict).filter(...).first()  # ORM session 缓存可能返回老对象
```

**修复组合**：
1. `_migrate` 用 `db.flush()` 强制 UPDATE 同步到 DB（同事务内）
2. for 循环用原生 SQL `INSERT ... ON CONFLICT DO NOTHING` 而不是 ORM `db.add()`
3. **不要用 `db.expire_all()`**（那会丢掉内存中的修改，让改名丢失）

### 坑 4：for row, in Row 解包

```python
# 错误：SQLAlchemy Row 是 1 个 Row 对象（不是 tuple），'for row, in [Row]' 会试图 unpack Row 失败
for row, in db.execute(text("SELECT a, b FROM t")):
    print(row[0])  # ❌ ValueError: too many values to unpack
```

```python
# 正确
for row in db.execute(text("SELECT a, b FROM t")):
    print(row[0], row[1])
```

### 坑 5：保留 `load_dotenv()`

删 `from dotenv import load_dotenv; load_dotenv()` 会让脚本读不到 `.env` 配置，DB 连接会失败。手动 patch 这两行不要漏。

### 坑 6：session.commit() 与 db.flush() 的区别

- `db.flush()`：把 SQL 发到 DB，但事务未提交（可回滚）
- `db.commit()`：把事务提交（不可回滚）
- 字典 seed 需要先 `_migrate → flush`（让改名可见），然后 `for 循环 add`，最后 `commit` 一次性提交所有改动