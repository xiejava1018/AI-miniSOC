"""dedupe scan menu icons (all were ri:radar-line, same as /browsing)

Revision ID: u3v4w5x6y7z8
Revises: t2u3v4w5x6y7
Create Date: 2026-08-27

- /scan 资产扫描        ri:radar-line -> ri:scan-2-line
- /scan/scanners 扫描器 ri:radar-line -> ri:cpu-line
- /scan/tasks 扫描任务  ri:radar-line -> ri:list-check-2
- /scan/findings 发现清单 ri:radar-line -> ri:search-eye-line
"""
from typing import Sequence, Union

from alembic import op

revision: str = "u3v4w5x6y7z8"
down_revision: Union[str, Sequence[str], None] = "t2u3v4w5x6y7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (path, parent_path, old_icon, new_icon)
_CHANGES = [
    ("/scan", None, "ri:radar-line", "ri:scan-2-line"),
    ("scanners", "/scan", "ri:radar-line", "ri:cpu-line"),
    ("tasks", "/scan", "ri:radar-line", "ri:list-check-2"),
    ("findings", "/scan", "ri:radar-line", "ri:search-eye-line"),
]


def _sql(changes, direction):
    stmts = []
    for path, parent, old, new in changes:
        cur, prev = (new, old) if direction == "up" else (old, new)
        stmts.append(f"""
            UPDATE soc_menus SET icon = '{cur}'
            WHERE path = '{path}' AND icon = '{prev}'
              AND parent_id {'IS NULL' if parent is None else f"= (SELECT id FROM soc_menus WHERE path='{parent}')"};
        """)
    return "".join(stmts)


def upgrade() -> None:
    op.execute(_sql(_CHANGES, "up"))


def downgrade() -> None:
    op.execute(_sql(_CHANGES, "down"))
