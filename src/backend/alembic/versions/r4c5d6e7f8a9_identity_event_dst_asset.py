"""identity events dst_asset_id backfill column (OH-P1.T6)

2026-10（issue #12）改为幂等：
`a6b7c8d9e0f1` 用 Base.metadata 建 `soc_identity_events`，而 ORM 的
IdentityEvent 已含 `dst_asset_id`，所以空库上该列在建表时就存在，
本迁移再 `op.add_column` 会 DuplicateColumn 报错。改成
`ADD COLUMN IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS`，两种库都能跑。

Revision ID: r4c5d6e7f8a9
Revises: q3b4c5d6e7f8
Create Date: 2026-10-07
"""
from alembic import op

# revision identifiers, used by Alembic.
revision = "r4c5d6e7f8a9"
down_revision = "q3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE soc_identity_events "
        "ADD COLUMN IF NOT EXISTS dst_asset_id UUID"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_identity_events_dst_asset "
        "ON soc_identity_events (dst_asset_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_identity_events_dst_asset")
    op.execute("ALTER TABLE soc_identity_events DROP COLUMN IF EXISTS dst_asset_id")
