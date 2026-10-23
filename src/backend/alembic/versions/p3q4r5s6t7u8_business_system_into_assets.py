"""
业务系统菜单移到 /assets 下，name/title 改名「业务系统」（2026-09-14）

变更：
- 业务系统菜单（id=74）
    parent_id:  5 (/system) → 2 (/assets)
    name:       'business-system' → 保持
    title:      '业务系统管理' → '业务系统'
    path:       'business-system'（保持，前端 URL 仍为 /assets/business-system）
    component:  '/system/business-system/index' → '/asset/business-system/index'
    sort_order: 8 → 3（放到资产列表 sort=2 之后）

- /assets 子菜单重排（避免 sort 冲突）：
    overview     sort 1（保持）
    list         sort 2（保持）
    detail/:id   sort 4（原 3 → 后移）
    compliance   sort 5（原 4 → 后移）
    reconciliation sort 6（原 5 → 后移）
    graph        sort 7（原 8 → 后移）

- 前端视图文件需同步迁移：views/system/business-system/ → views/asset/business-system/
  （迁移文件本身只改 DB schema；前端 .vue 文件由 git mv 同步处理）

幂等：每个 UPDATE 都加 WHERE 守卫，可重入。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p3q4r5s6t7u8"
down_revision: Union[str, None] = "q9r8s7t6u5v4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------------------------
    # 1. /assets 子菜单重排（按业务语义顺序：列表→详情→合规→稽核→图谱）
    # ------------------------------------------------------------------------
    # overview sort=1（保持不变，仅保险）
    bind.execute(sa.text(
        "UPDATE soc_menus SET sort_order = 1 "
        "WHERE parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL) "
        "AND path = 'overview'"
    ))
    # list sort=2
    bind.execute(sa.text(
        "UPDATE soc_menus SET sort_order = 2 "
        "WHERE parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL) "
        "AND path = 'list'"
    ))
    # detail sort=4（原 3，让位给业务系统）
    # 注意 path='detail/:id' 中冒号会被 SQLAlchemy 当绑定参数，用命名变量
    bind.execute(sa.text(
        "UPDATE soc_menus SET sort_order = 4 "
        "WHERE parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL) "
        "AND path = :detail_path"
    ), {"detail_path": "detail/:id"})
    # compliance sort=5
    bind.execute(sa.text(
        "UPDATE soc_menus SET sort_order = 5 "
        "WHERE parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL) "
        "AND path = 'compliance'"
    ))
    # reconciliation sort=6
    bind.execute(sa.text(
        "UPDATE soc_menus SET sort_order = 6 "
        "WHERE parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL) "
        "AND path = 'reconciliation'"
    ))
    # graph sort=7
    bind.execute(sa.text(
        "UPDATE soc_menus SET sort_order = 7 "
        "WHERE parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL) "
        "AND path = 'graph'"
    ))

    # ------------------------------------------------------------------------
    # 2. 业务系统菜单：移到 /assets 下 + 改名「业务系统」+ component 路径调整
    # ------------------------------------------------------------------------
    # 2026-10（issue #12）：原写 `parent_id = 5`（硬编码生产库 /system 的 id）。
    # 空库上 /system 并非 id=5，这条 UPDATE 静默 0 行 → 菜单留在 /system 下，
    # 而 k0m1n2o3p4q5 基线已在 /assets 下种了同名菜单 → 出现重复菜单。
    # 改为按 path 反查父菜单（不硬编码 id）。
    bind.execute(sa.text("""
        UPDATE soc_menus
        SET parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL),
            name = 'business-system',
            title = '业务系统',
            component = '/asset/business-system/index',
            sort_order = 3
        WHERE path = 'business-system'
          AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
    """))

    # 若 /assets 下已经有同名菜单（k0m1n2o3p4q5 基线已种），刚移过来的这份就是
    # 重复行 —— 同 path 同 component 会让前端生成两条一模一样的路由。
    # 同 (parent_id, path) 只保留最早插入的一行，其余删掉（连带其授权）。
    bind.execute(sa.text("""
        DELETE FROM soc_role_menus
        WHERE menu_id IN (
            SELECT id FROM soc_menus
            WHERE path = 'business-system'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL)
              AND id NOT IN (
                  SELECT min(id) FROM soc_menus
                  WHERE path = 'business-system'
                    AND parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL)
                  GROUP BY parent_id, path
              )
        )
    """))
    bind.execute(sa.text("""
        DELETE FROM soc_menus
        WHERE path = 'business-system'
          AND parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL)
          AND id NOT IN (
              SELECT min(id) FROM soc_menus
              WHERE path = 'business-system'
                AND parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL)
              GROUP BY parent_id, path
          )
    """))


def downgrade() -> None:
    bind = op.get_bind()

    # 1. 业务系统移回 /system
    bind.execute(sa.text("""
        UPDATE soc_menus
        SET parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL),
            name = 'business-system',
            title = '业务系统管理',
            component = '/system/business-system/index',
            sort_order = 8
        WHERE path = 'business-system'
          AND parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL)
    """))

    # 2. /assets 子菜单 sort 回原状
    for path, sort in [
        ('detail/:id', 3),
        ('compliance', 4),
        ('reconciliation', 5),
        ('graph', 8),
    ]:
        # 冒号路径 detail/:id 走命名变量避开 SQLAlchemy 解析
        path_key = 'detail_path' if ':' in path else 'path'
        bind.execute(sa.text(
            "UPDATE soc_menus SET sort_order = :sort "
            "WHERE parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL) "
            f"AND path = :{path_key}"
        ), {"sort": sort, path_key: path})
