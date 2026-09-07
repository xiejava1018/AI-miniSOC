"""rename /browsing 菜单为「行为分析」+ 行为画像上移到行为统计之后 (2026-09-06)

1) 顶级菜单 /browsing：name '行为检测' / title '上网行为' → 均改为 '行为分析'
   （API 层 title 取 `title or name`，两者一并改避免菜单管理页与侧边栏文案不一致）
2) 子菜单重排：行为画像(profile) 从 sort_order=7 提到 2（紧跟 行为统计=1），
   其余顺次后移：event 2→3, logs 3→4, baseline 4→5, blacklist 5→6, config 6→7。
   隐藏路由 profile/detail/:ip 保持 9 不动。

全部 UPDATE 按 path 定位并限定 parent=/browsing（子菜单 path 是相对名，
其它父菜单下也可能有同名 path，必须带 parent 约束）。

⚠️ 字面量内联而非绑定参数：本迁移刻意不用 `bind.execute(text(sql), {params})`。
`alembic upgrade --sql` 离线模式不会绑定运行期参数，会把 `:name` / `:path` 全
渲染成 NULL —— dry-run 输出会变成 `SET name=NULL, title=NULL` 且
`WHERE m.path = NULL`（永不匹配）。即：dry-run 预览与真实行为不一致，且一旦
真在离线模式执行会清空菜单名。这正是 CLAUDE.md 反复强调「迁移写纯 SQL」的原因。
此处值全是固定中文串与整数、无外部输入，内联无注入风险。

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


def _rename(name: str, title: str) -> str:
    return f"""
        UPDATE soc_menus
        SET name = '{name}', title = '{title}', updated_at = NOW()
        WHERE path = '/browsing' AND parent_id IS NULL
    """


def _reorder(path: str, sort_order: int) -> str:
    return f"""
        UPDATE soc_menus m
        SET sort_order = {sort_order}, updated_at = NOW()
        FROM soc_menus p
        WHERE p.path = '/browsing' AND p.parent_id IS NULL
          AND m.parent_id = p.id AND m.path = '{path}'
    """


def upgrade() -> None:
    op.execute(_rename("行为分析", "行为分析"))
    for path, (new_sort, _old) in _ORDER.items():
        op.execute(_reorder(path, new_sort))


def downgrade() -> None:
    op.execute(_rename("行为检测", "上网行为"))
    for path, (_new, old_sort) in _ORDER.items():
        op.execute(_reorder(path, old_sort))
