"""menu display cleanup: titles + /incidents path consistency (P3/ops-reorg 续)

Revision ID: k1l2m3n4o5p6
Revises: j1k2l3m4n5o6
Create Date: 2026-08-22

三件小事合并到一个迁移（避免再开一堆 micro-migration 污染 alembic 历史）：

1. /vulnerabilities (id=30) 加中文 title='脆弱性管理'
   - 现状：顶级菜单 title=NULL，侧边栏 fallback 显示英文 '/vulnerabilities'
   - 子菜单（overview/list 686/816 行）已实现，不是占位
2. /browsing (id=22) 加中文 title='上网行为'
   - 现状同上，6 个子菜单都真实现（71-412 行）
   - 命名参考 "行为统计概览" "行为基线" 等子菜单已有的「行为」用词
3. /incidents 顶级菜单下的子菜单（path='list'，当前 title='事件列表'）
   component 从 '/incident/index' 改为 '/incidents/index'
   - 前端视图目录 views/incident/ → views/incidents/（同时 git mv）
   - 对齐：URL '/incidents/list'（带 s）、后端 API '/api/v1/incidents'（带 s）、
     routesAlias.Incidents='/incidents/list'（带 s），唯一单数引用是文件目录

不影响的项（顺便说清楚，不动）：
- /reports (id=39) title='安全报告' 但 component=None —— 用户通过子菜单「报告列表」访问，
  顶级点开是空 layout（与 /system /assets 同款），不属占位，是设计选择
- routesAlias.Placeholder='/placeholder' —— 真占位页（views/placeholder/index.vue），
  当前没有被任何菜单引用，是基础设施
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "k1l2m3n4o5p6"
down_revision: Union[str, Sequence[str], None] = "j1k2l3m4n5o6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. /vulnerabilities 加中文 title
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET title = '脆弱性管理', updated_at = NOW()
            WHERE path = '/vulnerabilities' AND parent_id IS NULL
            """
        )
    )

    # 2. /browsing 加中文 title
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET title = '上网行为', updated_at = NOW()
            WHERE path = '/browsing' AND parent_id IS NULL
            """
        )
    )

    # 3. /incidents 子菜单的 component 从单数改复数（与 git mv 的文件目录对齐）
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET component = '/incidents/index', updated_at = NOW()
            WHERE m.path = 'list'
              AND m.parent_id = (SELECT id FROM soc_menus
                                 WHERE path = '/incidents' AND parent_id IS NULL)
              AND m.component = '/incident/index'
            """
        )
    )


def downgrade() -> None:
    # 反向：去掉 title（恢复 NULL），component 改回单数
    op.execute(
        sa.text(
            """
            UPDATE soc_menus m
            SET component = '/incident/index', updated_at = NOW()
            WHERE m.path = 'list'
              AND m.parent_id = (SELECT id FROM soc_menus
                                 WHERE path = '/incidents' AND parent_id IS NULL)
              AND m.component = '/incidents/index'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET title = NULL, updated_at = NOW()
            WHERE path = '/browsing' AND parent_id IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET title = NULL, updated_at = NOW()
            WHERE path = '/vulnerabilities' AND parent_id IS NULL
            """
        )
    )