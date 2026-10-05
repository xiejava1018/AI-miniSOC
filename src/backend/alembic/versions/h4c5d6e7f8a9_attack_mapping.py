"""ATT&CK 映射迁移（OH-4.4 · S6）

Revision ID: h4c5d6e7f8a9
Revises: g3b4c5d6e7f8
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "h4c5d6e7f8a9"
down_revision: Union[str, Sequence[str], None] = "g3b4c5d6e7f8"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None


def upgrade() -> None:
    op.create_table(
        "soc_attack_patterns",
        sa.Column("technique_id", sa.String(20), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("tactic", sa.String(20), nullable=False),
        sa.Column("url", sa.String(500)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "idx_soc_attack_patterns_tactic", "soc_attack_patterns", ["tactic"],
    )

    op.create_table(
        "soc_alert_attack_mappings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "technique_id", sa.String(20),
            sa.ForeignKey("soc_attack_patterns.technique_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("match_type", sa.String(20), nullable=False),
        sa.Column("match_value", sa.String(200), nullable=False),
        sa.Column("confidence", sa.Float, nullable=False, server_default="0.6"),
        sa.Column("source", sa.String(20), nullable=False, server_default="seed"),
        sa.Column("manual_override", sa.String(1), nullable=False,
                  server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_index(
        "uq_soc_alert_attack_mapping", "soc_alert_attack_mappings",
        ["match_type", "match_value", "technique_id"], unique=True,
    )
    op.create_index(
        "idx_soc_alert_attack_mapping_rule", "soc_alert_attack_mappings",
        ["match_value"],
    )


def downgrade() -> None:
    op.drop_index("idx_soc_alert_attack_mapping_rule",
                  table_name="soc_alert_attack_mappings")
    op.drop_index("uq_soc_alert_attack_mapping",
                  table_name="soc_alert_attack_mappings")
    op.drop_table("soc_alert_attack_mappings")
    op.drop_index("idx_soc_attack_patterns_tactic", table_name="soc_attack_patterns")
    op.drop_table("soc_attack_patterns")
