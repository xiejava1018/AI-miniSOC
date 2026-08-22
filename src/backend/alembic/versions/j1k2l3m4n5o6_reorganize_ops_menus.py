"""reorganize menus under 运维管理 (/ops) + rename 资产对账→资产稽核 (P3/ops-reorg)

Revision ID: j1k2l3m4n5o6
Revises: i3j4k5l6m7n8
Create Date: 2026-08-22

目的：
1. 新顶级菜单「运维管理」(path=/ops, sort=8，介于 /system 与 /reports 之间)
2. 把 4 个子菜单移到 /ops 下：
   - 任务中心           (原 /system 下 sort=90)
   - 数据健康           (原 /assets 下 sort=6)
   - 变更影响分析       (原 /assets 下 sort=7)
   - 知识库             (原顶级 /knowledge sort=65)
   新 sort_order 1/2/3/4
3. 资产对账 → 资产稽核（仅改 name/title；path 'reconciliation'、component、
   permissions（按钮 authMark: view/reconcile/resolve/report）都不动以减小影响）
4. /ops 本身**不**显式插 soc_role_menus —— X1 修复后的"父菜单作为容器"逻辑
   （menu_service.get_menu_tree 中的 parent_ids 集合）会自动从被授权的子菜单
   反推出 /ops 必须显示。新顶级菜单 permissions='[]' 无按钮。

幂等约定（项目历史教训）：
- INSERT ... WHERE NOT EXISTS / UPDATE 都带 WHERE 限定重复跑不爆
- 不在 UPDATE 后回读 .scalar()（--sql dry-run 下 NoneType.spawn）
- 父菜单按 path 子查询动态解析，不硬编码 id
- 顺序：先 INSERT /ops，再 UPDATE 4 个子菜单 parent_id（FK 必须有父才能指）
- downgrade 顺序相反：先删 /ops，再复原 4 个 parent_id（FK 约束要求父先存在）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "j1k2l3m4n5o6"
down_revision: Union[str, Sequence[str], None] = "i3j4k5l6m7n8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- 1. 新顶级菜单「运维管理」----------
    # component 用 /index/index（其它容器 /system /assets /incidents /alerts 同款）
    op.execute(
        sa.text(
            """
            INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                                   sort_order, is_visible, permissions, created_at, updated_at)
            SELECT NULL, '运维管理', '运维管理', '/ops', 'ri:tools-line', '/index/index',
                   8, TRUE, '[]'::jsonb, NOW(), NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM soc_menus WHERE path = '/ops' AND parent_id IS NULL
            )
            """
        )
    )

    # ---------- 2. 把 4 个子菜单移到 /ops 下 + 重新设 sort_order ----------

    # 任务中心: /system → /ops，sort 90 → 1
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET parent_id = (SELECT id FROM soc_menus WHERE path = '/ops' AND parent_id IS NULL),
                sort_order = 1,
                updated_at = NOW()
            WHERE m.path = 'task-center'
              AND m.parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )

    # 数据健康: /assets → /ops，sort 6 → 2
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET parent_id = (SELECT id FROM soc_menus WHERE path = '/ops' AND parent_id IS NULL),
                sort_order = 2,
                updated_at = NOW()
            WHERE m.path = 'data-health'
              AND m.parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL)
            """
        )
    )

    # 变更影响分析: /assets → /ops，sort 7 → 3
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET parent_id = (SELECT id FROM soc_menus WHERE path = '/ops' AND parent_id IS NULL),
                sort_order = 3,
                updated_at = NOW()
            WHERE m.path = 'impact-analysis'
              AND m.parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL)
            """
        )
    )

    # 知识库: 顶级 → /ops 下，sort 65 → 4
    # path 同步规范化：'/knowledge' → 'knowledge'（顶级约定带斜杠，子菜单约定不带）
    # WHERE 只用 path，不绑 parent_id — 避免重跑时 path 已规范化但 parent_id 已改过的中间态漏更新
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET parent_id = (SELECT id FROM soc_menus WHERE path = '/ops' AND parent_id IS NULL),
                path = 'knowledge',
                sort_order = 4,
                updated_at = NOW()
            WHERE m.path = '/knowledge'
            """
        )
    )

    # ---------- 3. 资产对账 → 资产稽核（仅改 name/title）----------
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET name = '资产稽核',
                title = '资产稽核',
                updated_at = NOW()
            WHERE m.path = 'reconciliation'
              AND m.parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL)
            """
        )
    )


def downgrade() -> None:
    # 顺序：先恢复子菜单原位 + 改回 reconciliation 命名，最后删 /ops
    # （FK 要求父菜单存在；最后删 /ops 也避免空库场景的级联问题）

    # 1. 资产稽核 → 资产对账
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET name = '资产对账',
                title = '资产对账',
                updated_at = NOW()
            WHERE m.path = 'reconciliation'
              AND m.parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL)
            """
        )
    )

    # 2. 任务中心: /ops → /system，sort 1 → 90
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL),
                sort_order = 90,
                updated_at = NOW()
            WHERE m.path = 'task-center'
              AND m.parent_id = (SELECT id FROM soc_menus WHERE path = '/ops' AND parent_id IS NULL)
            """
        )
    )

    # 3. 数据健康: /ops → /assets，sort 2 → 6
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL),
                sort_order = 6,
                updated_at = NOW()
            WHERE m.path = 'data-health'
              AND m.parent_id = (SELECT id FROM soc_menus WHERE path = '/ops' AND parent_id IS NULL)
            """
        )
    )

    # 4. 变更影响分析: /ops → /assets，sort 3 → 7
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL),
                sort_order = 7,
                updated_at = NOW()
            WHERE m.path = 'impact-analysis'
              AND m.parent_id = (SELECT id FROM soc_menus WHERE path = '/ops' AND parent_id IS NULL)
            """
        )
    )

    # 5. 知识库: /ops → 顶级，sort 4 → 65（path 同步恢复 '/knowledge'）
    # path 同时容错 knowledge 与 /knowledge（处理中间态）
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET parent_id = NULL,
                path = '/knowledge',
                sort_order = 65,
                updated_at = NOW()
            WHERE m.path IN ('knowledge', '/knowledge')
              AND m.parent_id = (SELECT id FROM soc_menus WHERE path = '/ops' AND parent_id IS NULL)
            """
        )
    )

    # 6. 删除 /ops 顶级菜单
    op.execute(
        sa.text(
            """
            DELETE FROM soc_menus WHERE path = '/ops' AND parent_id IS NULL
            """
        )
    )