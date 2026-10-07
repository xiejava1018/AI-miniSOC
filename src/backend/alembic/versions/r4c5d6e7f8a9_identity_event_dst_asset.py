"""identity events dst_asset_id backfill column (OH-P1.T6)

Revision ID: r4c5d6e7f8a9
Revises: q3b4c5d6e7f8
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "r4c5d6e7f8a9"
down_revision = "q3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "soc_identity_events",
        sa.Column("dst_asset_id", UUID(as_uuid=True), nullable=True,
                  comment="OH-P1.T6：dst_ip 经 EntityResolver 锚定的资产 id"),
    )
    op.create_index(
        "ix_identity_events_dst_asset", "soc_identity_events",
        ["dst_asset_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_identity_events_dst_asset",
                  table_name="soc_identity_events")
    op.drop_column("soc_identity_events", "dst_asset_id")
