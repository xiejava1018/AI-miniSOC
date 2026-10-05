"""UEBA 僵尸工单防重索引（UEBA×S10 联动）

同资产同时只允许一张未终态 ueba_zombie 工单。

Revision ID: k7b8c9d0e1f2
Revises: j6a7b8c9d0e1
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "k7b8c9d0e1f2"
down_revision: Union[str, Sequence[str], None] = "j6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_soc_remediation_ueba_active", "soc_remediation_tickets",
        ["asset_id"], unique=True,
        postgresql_where=sa.text(
            "source_type = 'ueba_zombie' AND status NOT IN ('verified', 'cancelled')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_soc_remediation_ueba_active", table_name="soc_remediation_tickets")
