"""fix invalid menu icons (P3/ops-reorg 续 3)

Revision ID: m1n2o3p4q5r6
Revises: l1m2n3o4p5q6
Create Date: 2026-08-22

之前 l1m2n3o4p5q6 给 reports/list 补了 icon、对 impact-analysis 修了 HTML entity，
但仍有2 个菜单 icon 不显示：

1. /assets/reconciliation (资产稽核) icon='ri:git-compare-line'
   — iconify-json/ri 库中**没有** git-compare-line，只有 git-compare-fill / git-commit-line 等
   — 改 'ri:scales-3-line'（天秤，审计主题意象）

2. /reports (安全报告) icon='Document'
   — 'Document' 是 Material Icons 字符串（Font class），不是 iconify 格式
   — iconify 找不到所以完全渲染不出
   — 改 'ri:file-shield-2-line'（文件 + 盾牌，安全报告主题）

注：本迁移只改 icon 字符串，菜单 title/sort 等不动。
前端 /asset/reconciliation/index.vue 里的"资产对账"显示也需改为"资产稽核"（与菜单名统一），
那是 .vue 文件编辑，不在迁移范围。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "m1n2o3p4q5r6"
down_revision: Union[str, Sequence[str], None] = "l1m2n3o4p5q6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. /assets/reconciliation: git-compare-line → scales-3-line
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET icon = 'ri:scales-3-line', updated_at = NOW()
            WHERE m.path = 'reconciliation'
              AND m.parent_id = (SELECT id FROM soc_menus
                                 WHERE path = '/assets' AND parent_id IS NULL)
            """
        )
    )

    # 2. /reports: 'Document' → 'ri:file-shield-2-line'
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET icon = 'ri:file-shield-2-line', updated_at = NOW()
            WHERE path = '/reports' AND parent_id IS NULL
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET icon = 'Document', updated_at = NOW()
            WHERE path = '/reports' AND parent_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET icon = 'ri:git-compare-line', updated_at = NOW()
            WHERE m.path = 'reconciliation'
              AND m.parent_id = (SELECT id FROM soc_menus
                                 WHERE path = '/assets' AND parent_id IS NULL)
            """
        )
    )