"""rename /browsing 菜单为「行为分析」+ 行为画像上移到行为统计之后 (2026-09-06)

1) 顶级菜单 /browsing：name '行为检测' / title '上网行为' → 均改为 '行为分析'
   （API 层 title 取 `title or name`，两者一并改避免菜单管理页与侧边栏文案不一致）
2) 子菜单重排：行为画像(profile) 从 sort_order=7 提到 2（紧跟 行为统计=1），
   其余顺次后移：event 2→3, logs 3→4, baseline 4→5, blacklist 5→6, config 6→7。
   隐藏路由 profile/detail/:ip 保持 9 不动。

全部 UPDATE 按 path 定位并限定 parent=/browsing（子菜单 path 是相对名，
其它父菜单下也可能有同名 path，必须带 parent 约束）。纯 SQL，--sql dry-run 可跑。

Revision ID: c1d2e3f4g5h6
Revises: b1c2d3e4f5g6
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4g5h6"
down_revision: Union[str, Sequence[str], None] = "b1c2d3e4f5g6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# path -> (新 sort_order, 旧 sort_order)
_ORDER = {
    "statistics": (1, 1),
    "profile": (2, 7),
    "event": (3, 2),
    "logs": (4, 3),
    "baseline": (5, 4),
    "blacklist": (6, 5),
    "config": (7, 6),
}

_RENAME_SQL = """
    UPDATE soc_menus
    SET name = :name, title = :title, updated_at = NOW()
    WHERE path = '/browsing' AND parent_id IS NULL
"""

_REORDER_SQL = """
    UPDATE soc_menus m
    SET sort_order = :sort_order, updated_at = NOW()
    FROM soc_menus p
    WHERE p.path = '/browsing' AND p.parent_id IS NULL
      AND m.parent_id = p.id AND m.path = :path
"""


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(_RENAME_SQL), {"name": "行为分析", "title": "行为分析"})
    for path, (new_sort, _old) in _ORDER.items():
        bind.execute(sa.text(_REORDER_SQL), {"path": path, "sort_order": new_sort})


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(_RENAME_SQL), {"name": "行为检测", "title": "上网行为"})
    for path, (_new, old_sort) in _ORDER.items():
        bind.execute(sa.text(_REORDER_SQL), {"path": path, "sort_order": old_sort})
