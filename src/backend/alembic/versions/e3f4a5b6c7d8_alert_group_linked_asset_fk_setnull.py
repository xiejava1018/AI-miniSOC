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

2026-11-10 空库安装修复（补注）
------------------------------
按 CLAUDE.md §4.3 红线 6 在真·空库上跑 `upgrade head` 时，本迁移报：

    ProgrammingError: column "linked_asset_id" referenced in foreign key
    constraint does not exist

根因：soc_alert_group_analyses 由 e2f3a4b5c6d7 用裸 SQL
`CREATE TABLE IF NOT EXISTS` 建立，该表只有 9 列，**不含 linked_asset_id**
（且多出 verdict_at/ai_model/explanation 三个 ORM 里没有的列）。老库上
`IF NOT EXISTS` 让这条 CREATE 被跳过（表早已由 create_all 按 ORM 建好），
所以列集正确；**空库上则由这条 CREATE 生效 → 列集缺列 → 本迁移炸掉**。

修法（本迁移内补列，使空库能跑过本步）：
在 ADD CONSTRAINT 之前，若目标列不存在则先 ADD COLUMN IF NOT EXISTS。
这样空库/老库都能通过，且列的最终定义与 ORM 模型一致。

正式补列迁移见 n2o3p4q5r6s7_fix_alert_group_analyses_columns.py
（负责把列集补齐到 ORM 模型的完整 17 列 + 索引）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
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
        sa.text(
            """
        SELECT conname FROM pg_constraint
        WHERE contype = 'f'
          AND conrelid = CAST(:table AS regclass)
          AND confrelid = 'soc_assets'::regclass
          AND pg_get_constraintdef(oid) ILIKE '%' || :column || '%'
        """
        ),
        {"table": table, "column": column},
    ).fetchall()
    return [r[0] for r in rows]


def _column_exists(bind, table, column) -> bool:
    row = bind.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = current_schema() "
            "  AND table_name = :table AND column_name = :column LIMIT 1"
        ),
        {"table": table, "column": column},
    ).fetchone()
    return row is not None


def upgrade() -> None:
    bind = op.get_bind()
    for table, column in _TARGETS:
        # 空库修复：列不存在（e2f3a4b5c6d7 的 CREATE TABLE IF NOT EXISTS
        # 建出的列集与 ORM 模型不一致）时先补列，否则 ADD CONSTRAINT 报
        # UndefinedColumn。已有列的老库走「列存在」分支，行为不变。
        if not _column_exists(bind, table, column):
            bind.execute(
                sa.text(
                    f"ALTER TABLE {table} "
                    f"ADD COLUMN IF NOT EXISTS {column} UUID"
                )
            )
        for conname in _existing_fks(bind, table, column):
            bind.execute(
                sa.text(f'ALTER TABLE {table} DROP CONSTRAINT IF EXISTS "{conname}"')
            )
        bind.execute(
            sa.text(
                f"ALTER TABLE {table} ADD CONSTRAINT {table}_{column}_fkey "
                f"FOREIGN KEY ({column}) REFERENCES soc_assets(id) ON DELETE SET NULL"
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table, column in _TARGETS:
        bind.execute(
            sa.text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_{column}_fkey")
        )
        bind.execute(
            sa.text(
                f"ALTER TABLE {table} ADD CONSTRAINT {table}_{column}_fkey "
                f"FOREIGN KEY ({column}) REFERENCES soc_assets(id)"
            )
        )
