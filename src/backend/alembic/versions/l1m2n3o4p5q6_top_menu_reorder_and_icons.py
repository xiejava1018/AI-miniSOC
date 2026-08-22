"""top menu reorder + chinese titles + missing icons (P3/ops-reorg 续 2)

Revision ID: l1m2n3o4p5q6
Revises: k1l2m3n4o5p6
Create Date: 2026-08-22

三件事一起做，避免再来一条 micro-migration：

1. 顶级菜单重排序（按用户指定顺序）
   新顺序：dashboard(1) assets(2) vulnerabilities(3) incidents(4) alerts(5)
           browsing(6) reports(7) ops(8) system(9)
   变动：/reports sort 50→7, /system sort 7→9
        （其它 7 个 sort 不变，仍是 1/2/3/4/5/6/8）

2. 顶级菜单补中文 title（侧边栏不再 fallback 显示英文 path）
   /dashboard title='概览仪表板'
   /assets    title='资产管理'
   /system    title='系统管理'
   （/vulnerabilities /incidents /alerts /browsing /ops /reports 已有中文 title）

3. 补/修 icon
   /reports/list           icon: NULL     → 'ri:file-list-2-line'   (唯一真正无 icon)
   /ops/impact-analysis    icon: '&#xe6a0;' → 'ri:flow-chart'       (HTML entity 不会渲染)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "l1m2n3o4p5q6"
down_revision: Union[str, Sequence[str], None] = "k1l2m3n4o5p6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- 1. 顶级菜单重排序 ----------
    # /reports: 50 → 7
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 7, updated_at = NOW()
            WHERE path = '/reports' AND parent_id IS NULL
            """
        )
    )
    # /system: 7 → 9
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 9, updated_at = NOW()
            WHERE path = '/system' AND parent_id IS NULL
            """
        )
    )

    # ---------- 2. 补顶级中文 title ----------
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET title = '概览仪表板', updated_at = NOW()
            WHERE path = '/dashboard' AND parent_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET title = '资产管理', updated_at = NOW()
            WHERE path = '/assets' AND parent_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET title = '系统管理', updated_at = NOW()
            WHERE path = '/system' AND parent_id IS NULL
            """
        )
    )

    # ---------- 3. 补/修 icon ----------
    # /reports/list: NULL → ri:file-list-2-line
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET icon = 'ri:file-list-2-line', updated_at = NOW()
            WHERE m.path = 'list'
              AND m.parent_id = (SELECT id FROM soc_menus
                                 WHERE path = '/reports' AND parent_id IS NULL)
              AND (m.icon IS NULL OR m.icon = '')
            """
        )
    )
    # /ops/impact-analysis: '&#xe6a0;' (HTML entity 不渲染) → 'ri:flow-chart'
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET icon = 'ri:flow-chart', updated_at = NOW()
            WHERE path = 'impact-analysis'
              AND parent_id = (SELECT id FROM soc_menus
                               WHERE path = '/ops' AND parent_id IS NULL)
            """
        )
    )


def downgrade() -> None:
    # 1. icon 回退
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET icon = '&#xe6a0;', updated_at = NOW()
            WHERE path = 'impact-analysis'
              AND parent_id = (SELECT id FROM soc_menus
                               WHERE path = '/ops' AND parent_id IS NULL)
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET icon = NULL, updated_at = NOW()
            WHERE m.path = 'list'
              AND m.parent_id = (SELECT id FROM soc_menus
                                 WHERE path = '/reports' AND parent_id IS NULL)
            """
        )
    )
    # 2. title 回退
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET title = NULL, updated_at = NOW()
            WHERE path = '/system' AND parent_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET title = NULL, updated_at = NOW()
            WHERE path = '/assets' AND parent_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET title = NULL, updated_at = NOW()
            WHERE path = '/dashboard' AND parent_id IS NULL
            """
        )
    )
    # 3. sort 回退
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 7, updated_at = NOW()
            WHERE path = '/system' AND parent_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET sort_order = 50, updated_at = NOW()
            WHERE path = '/reports' AND parent_id IS NULL
            """
        )
    )