"""behavior profile cat_by_block / workday / weekend columns (Phase 补齐)

对标《上网行为画像报告》：工作日/周末占比 + 分类x时段堆叠（cat_block_stack）。

Revision ID: z5a6b7c8d9e0
Revises: y4z5a6b7c8d9
Create Date: 2026-09-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "z5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "y4z5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "ALTER TABLE soc_behavior_profiles "
        "ADD COLUMN IF NOT EXISTS cat_by_block JSONB"))
    bind.execute(sa.text(
        "ALTER TABLE soc_behavior_profiles "
        "ADD COLUMN IF NOT EXISTS workday INTEGER NOT NULL DEFAULT 0"))
    bind.execute(sa.text(
        "ALTER TABLE soc_behavior_profiles "
        "ADD COLUMN IF NOT EXISTS weekend INTEGER NOT NULL DEFAULT 0"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "ALTER TABLE soc_behavior_profiles "
        "DROP COLUMN IF EXISTS cat_by_block, "
        "DROP COLUMN IF EXISTS workday, DROP COLUMN IF EXISTS weekend"))
