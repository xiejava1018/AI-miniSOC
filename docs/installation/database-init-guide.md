# 数据库初始化指南

> ⚠️ **本文档已于 2026-10 重写（GitHub issue #12）。**
> 旧版本引导读者手工执行 `scripts/database/init_soc_assets.sql`，
> 但该文件**在仓库中不存在**，且里面的表结构（`id TEXT` / `asset_ip INET`）
> 早已与 ORM 不符。照着做必然失败。
>
> **现在建表只有一条正确路径：`alembic upgrade head`。**
> 菜单、角色、默认管理员都由迁移一并种好，不需要任何手工 SQL。

---

## 前提条件

1. **PostgreSQL 16+** 已安装并运行
2. 已创建目标数据库（库名见 `.env` 的 `DB_NAME`，默认 `AI-miniSOC-db`）
3. 已在仓库根目录配置好 `.env`（`DB_HOST` / `DB_PORT` / `DB_NAME` / `DB_USER` / `DB_PASSWORD`）

---

## 标准做法（唯一推荐）

```bash
cd src/backend

# 一步完成：建表 + 种 61 行菜单树 + 种 6 个角色 + 建默认 admin 账号
../../venv/bin/python -m alembic -c alembic.ini upgrade head
```

> 必须 `cd src/backend` —— `alembic.ini` 用 `%(here)s` 定位脚本目录，
> 在仓库根目录执行会找不到配置。

### 验证结果

```bash
../../venv/bin/python -m alembic -c alembic.ini heads
# 期望：n0b1c2d3e4f5 (head)   —— 有且仅有一个 head

../../venv/bin/python -m alembic -c alembic.ini current
# 期望：n0b1c2d3e4f5 (head)

psql "$DATABASE_URL" <<'SQL'
select count(*) as menus       from soc_menus;        -- 61
select count(*) as top_menus   from soc_menus where parent_id is null;  -- 11
select count(*) as roles       from soc_roles;        -- 6
select count(*) as users       from soc_users;        -- 1（admin）
select username, status from soc_users;              -- admin | active
SQL
```

### 默认登录账号

| 用户名 | 密码 | 角色 |
|---|---|---|
| `admin` | `Admin@123456` | admin |

🚨 **首次登录后立即改密**（系统管理 → 用户管理）。

部署时想直接指定密码：

```bash
DEFAULT_ADMIN_PASSWORD='你的强密码' ../../venv/bin/python -m alembic -c alembic.ini upgrade head
```

该迁移幂等：已存在 `admin` 时不会覆盖密码，重跑 `upgrade head` 安全。

---

## 多环境：三个库严格分离

| 库 | 用途 | 配置位置 |
|---|---|---|
| `AI-miniSOC-db` | 生产 | 服务器 `src/backend/.env` |
| `AI-miniSOC-testdb` | 本地开发 | 本地仓库 `.env` |
| `AI-miniSOC-db_test` | pytest | `TEST_DB_NAME` / `TEST_DATABASE_URL` |

临时指定目标库（env 优先于 `.env`）：

```bash
DB_NAME=AI-miniSOC-db_test ../../venv/bin/python -m alembic -c alembic.ini upgrade head
```

**绝对不要**让本地 `.env` 指向生产库。

---

## 故障排除

### `Multiple head revisions are present`

链被改成了多头。检查：

```bash
../../venv/bin/python -m alembic -c alembic.ini heads
```

应只输出一个 head。若出现多个，说明某个迁移的 `down_revision` 写错或重复，
新迁移必须挂在当前唯一 head 之下。

### `relation "soc_scanner_tasks" does not exist`

代码版本过旧 —— 扫描器四表由 `s1a2b3c4d5e6` 基线补齐。先 `git pull` 再重跑。

### `violates foreign key constraint "soc_menus_parent_id_fkey"`

某个迁移用硬编码 id 定位父菜单（`parent_id = 22`），而空库该 id 属于别的菜单。
菜单必须按 `path` 反查父菜单。本仓库已加回归测试
`tests/test_fresh_install_bootstrap.py::test_no_migration_hardcodes_menu_parent_id`
拦截此类写法。

### 迁移跑到一半失败

PostgreSQL DDL 是事务性的，失败会整体回滚，`alembic_version` 不会前进。
修正问题后直接重跑 `upgrade head` 即可，不需要手工清理。

### 想从零重建（丢弃所有数据）

```bash
../../venv/bin/python -m alembic -c alembic.ini downgrade base
../../venv/bin/python -m alembic -c alembic.ini upgrade head
```

⚠️ 会丢数据。仅限开发环境。

---

## 相关文档

- 命名规范（`soc_` 前缀）：`docs/design/database-naming-conventions.md`
- 部署全流程：`README.md` → 快速开始
- 回归测试：`src/backend/tests/test_fresh_install_bootstrap.py`

---

**重写日期**: 2026-10-19
**原因**: GitHub issue #12 —— 旧文档指向不存在的脚本，导致部署者卡死在初始化步骤