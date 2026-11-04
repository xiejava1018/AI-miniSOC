"""alert_group linked_asset_id FK 改为 ON DELETE SET NULL

Revision ID: e3f4a5b6c7d8
Revises: c7d8e9f0a1b2
Create Date: 2026-11-04

问题：soc_alert_groups / soc_alert_group_analyses 的 linked_asset_id 外键为
NO ACTION，删除被告警分组关联的资产时触发 ForeignKeyViolation → API 500
（2026-11-04 删除 127.0.0.1 资产报错即此因）。

修复：两个 FK 重建为 ON DELETE SET NULL（linked_asset_id 只是软关联的
快照/缓存字段，资产删除后置空即可）。

约束名不硬编码：按 pg_constraint 按 表+列 动态查出后 DROP，再重建。
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (表, 列) → 需要重建 FK 的目标
_TARGETS = [
    ("soc_alert_groups", "linked_asset_id"),
    ("soc_alert_group_analyses", "linked_asset_id"),
]


def _existing_fks(bind, table, column):
    rows = bind.execute(
        """
        SELECT conname FROM pg_constraint
        WHERE contype = 'f'
          AND conrelid = :table::regclass
          AND confrelid = 'soc_assets'::regclass
          AND pg_get_constraintdef(oid) ILIKE '%' || :column || '%'
        """,
        {"table": table, "column": column},
    ).fetchall()
    return [r[0] for r in rows]


def upgrade() -> None:
    bind = op.get_bind()
    for table, column in _TARGETS:
        for conname in _existing_fks(bind, table, column):
            bind.execute(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{conname}"')
        bind.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_{column}_fkey "
            f"FOREIGN KEY ({column}) REFERENCES soc_assets(id) ON DELETE SET NULL"
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table, column in _TARGETS:
        bind.execute(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_{column}_fkey")
        bind.execute(
            f"ALTER TABLE {table} ADD CONSTRAINT {table}_{column}_fkey "
            f"FOREIGN KEY ({column}) REFERENCES soc_assets(id)"
        )
