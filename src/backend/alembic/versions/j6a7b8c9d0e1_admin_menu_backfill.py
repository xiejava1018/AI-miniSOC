"""admin 角色菜单授权补齐（dev testdb 修复）

背景
----
本仓库 dev testdb 上 admin (role_id=1) 的 soc_role_menus 缺少 6 项授权：

  - id=71 配置中心（顶级容器）
  - id=62 配置管理（/config/config-center）
  - id=64 数据源管理（/config/data-source）
  - id=68 AI 模型管理（/config/ai-provider）
  - id=72 资产图谱（/assets/graph）
  - id=77 图谱性能看板（/assets/graph/perf-dashboard）

CLAUDE.md §4.3 红线 + §1.3「菜单树粒度」已经指出：子菜单须自身被授权，
父菜单只是容器。这 6 项里 id=62/64/68/72/77 是子菜单（必授），id=71
是顶级容器（CLAUDE.md §1.3 + MenuService 算法②：当子菜单授权后会从子
菜单 parent_id 反推父容器到 parent_ids，故顶级 71 会被隐式保留，
但仍然显式授权更清晰、不依赖服务层反向推断）。

CLAUDE.md §1.3 admin bypass 端点级守卫，但**菜单可见性**仍由 soc_role_menus
控制（admin 不是「看见一切菜单」的简写）。本迁移只补 admin 的菜单授权，
不动其他角色、不动菜单表、不动业务表。

修复点（与 i4j5k6l7m8n9_reorganize_config_menus.py 同一个 root cause）
----
i4j5k6l7m8n9 把 3 个配置中心子菜单从 /system 移到新建顶级 /config 下，
**只改 parent_id，没碰 soc_role_menus** —— admin 在 dev testdb 上从未
获得过 id=71 的显式授权，导致 MenuService 过滤后整个 /config 容器消失。

执行策略
--------
1. NOT EXISTS 守卫：幂等，已授权的库再次跑也只跳过。
2. JOIN 子查询定位 admin role / menu id，不硬编码 id（CLAUDE.md §4.3 红线 2）。
4. WHERE 条件用 path 而非 name（CLAUDE.md §4.3 教训：菜单 path 是不变式，
   name/title 在历史迁移中曾被中英混用过，path 稳定）。
5. 容器菜单 id=71 给 NULL permissions（容器无按钮）；
   功能菜单 id=62/64/68/72/77 从 soc_menus.permissions JSONB 抽取 authMark
   列表（与 d2e3f4g5h6i7 授权模式一致）。
6. JSONB 用 CAST(:perms AS jsonb) 风格（CLAUDE.md §4.3 红线 4：`:perms::jsonb`
   会被当绑定参数报错）。

down_revision 挂 i5d6e7f8a9b0（dev testdb 当前 head）。

Revision ID: j6a7b8c9d0e1
Revises: i5d6e7f8a9b0
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "j6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "i5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # ----- 1. 容器菜单 + 功能菜单（按 path 定位，不硬编码 id） -----
    # 容器菜单: id=71 配置中心（path=/config, parent_id IS NULL）
    #   → permissions=NULL（容器无按钮）
    # 功能菜单: id=62/64/68/72/77 → permissions 从 soc_menus.permissions 抽 authMark
    bind.execute(sa.text("""
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, m.id,
               CASE
                 WHEN m.path = '/config' AND m.parent_id IS NULL
                   THEN NULL
                 ELSE CAST(
                   (SELECT jsonb_agg(e->>'authMark')
                    FROM jsonb_array_elements(m.permissions) e) AS jsonb
                 )
               END
        FROM soc_roles r
        CROSS JOIN soc_menus m
        WHERE r.code = 'admin'
          AND (
                (m.path = '/config' AND m.parent_id IS NULL)
             OR (m.path IN ('config-center','data-source','ai-provider') AND m.parent_id IS NOT NULL)
             OR (m.path = 'graph' AND m.parent_id IS NOT NULL)
             OR (m.path = 'graph/perf-dashboard' AND m.parent_id IS NOT NULL)
          )
          AND NOT EXISTS (
            SELECT 1 FROM soc_role_menus rm
            WHERE rm.role_id = r.id AND rm.menu_id = m.id
          )
    """))


def downgrade() -> None:
    bind = op.get_bind()

    # 镜像撤销：只删本次新增的 6 项授权
    bind.execute(sa.text("""
        DELETE FROM soc_role_menus rm
        USING soc_roles r, soc_menus m
        WHERE rm.role_id = r.id AND rm.menu_id = m.id
          AND r.code = 'admin'
          AND (
                (m.path = '/config' AND m.parent_id IS NULL)
             OR (m.path IN ('config-center','data-source','ai-provider') AND m.parent_id IS NOT NULL)
             OR (m.path = 'graph' AND m.parent_id IS NOT NULL)
             OR (m.path = 'graph/perf-dashboard' AND m.parent_id IS NOT NULL)
          )
    """))