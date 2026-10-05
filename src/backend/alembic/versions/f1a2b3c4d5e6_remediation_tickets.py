"""OH-4.6 整改工单表

Revision ID: f1a2b3c4d5e6
Revises: e9f0a1b2c3d4
Create Date: 2026-10-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "e9f0a1b2c3d4"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None


def upgrade() -> None:
    op.create_table(
        "soc_remediation_tickets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column(
            "reconciliation_id", UUID(as_uuid=True),
            sa.ForeignKey("soc_asset_reconciliations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "compliance_finding_id", UUID(as_uuid=True),
            sa.ForeignKey("soc_compliance_findings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "asset_id", UUID(as_uuid=True),
            sa.ForeignKey("soc_assets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("detail", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.String(20), nullable=False, server_default="open"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("assignee", sa.String(255)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_by", sa.String(255)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolve_note", sa.Text()),
        sa.Column("verified_by", sa.String(255)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("occurrence_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "idx_soc_remediation_status", "soc_remediation_tickets",
        ["status", "created_at"],
    )
    op.create_index(
        "idx_soc_remediation_asset", "soc_remediation_tickets", ["asset_id"],
    )
    op.create_index(
        "idx_soc_remediation_assignee", "soc_remediation_tickets",
        ["assignee", "status"],
    )
    # 防重复派单：同来源同时只允许一张未终态工单
    op.create_index(
        "uq_soc_remediation_recon_active", "soc_remediation_tickets",
        ["reconciliation_id"], unique=True,
        postgresql_where=sa.text(
            "source_type = 'reconciliation' AND status NOT IN ('verified', 'cancelled')"
        ),
    )
    op.create_index(
        "uq_soc_remediation_comp_active", "soc_remediation_tickets",
        ["compliance_finding_id"], unique=True,
        postgresql_where=sa.text(
            "source_type = 'compliance' AND status NOT IN ('verified', 'cancelled')"
        ),
    )


def downgrade() -> None:
    op.drop_index("uq_soc_remediation_comp_active", table_name="soc_remediation_tickets")
    op.drop_index("uq_soc_remediation_recon_active", table_name="soc_remediation_tickets")
    op.drop_index("idx_soc_remediation_assignee", table_name="soc_remediation_tickets")
    op.drop_index("idx_soc_remediation_asset", table_name="soc_remediation_tickets")
    op.drop_index("idx_soc_remediation_status", table_name="soc_remediation_tickets")
    op.drop_table("soc_remediation_tickets")
