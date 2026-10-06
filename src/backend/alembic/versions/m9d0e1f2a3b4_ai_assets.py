"""OH-4.13 S13 AI 资产六类建模

创建 soc_ai_assets 表（kind/status/risk 枚举 + 共同字段 + details JSONB）。
六类共用单表 + kind 枚举：model/data/agent/tool/credential/compute。
credential 类型合规：details 禁存 plaintext 凭据，校验在 service 层做。

Revision ID: m9d0e1f2a3b4
Revises: l8c9d0e1f2a3
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "m9d0e1f2a3b4"
down_revision: Union[str, Sequence[str], None] = "l8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None


def upgrade() -> None:
    # create_type=False 让 create_table 内部创建（PG ENUM 只建一次）
    kind_enum = sa.Enum(
        "model", "data", "agent", "tool", "credential", "compute",
        name="ai_asset_kind", create_type=False,
    )
    status_enum = sa.Enum(
        "registered", "shadow", "sanctioned", "decommissioned",
        name="ai_asset_status", create_type=False,
    )
    risk_enum = sa.Enum(
        "low", "medium", "high", "critical",
        name="ai_asset_risk", create_type=False,
    )

    op.create_table(
        "soc_ai_assets",
        sa.Column("id", UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"),
                  primary_key=True),
        sa.Column("kind", kind_enum, nullable=False, index=True),
        sa.Column("name", sa.String(200), nullable=False, index=True),
        sa.Column("provider", sa.String(100)),
        sa.Column("version", sa.String(64)),
        sa.Column("owner", sa.String(255)),
        sa.Column("business_unit", sa.String(100)),
        sa.Column("business_system_id", UUID(as_uuid=True),
                  sa.ForeignKey("soc_business_systems.id",
                                ondelete="SET NULL"),
                  nullable=True, index=True),
        sa.Column("status", status_enum, nullable=False,
                  server_default="registered", index=True),
        sa.Column("risk_level", risk_enum, nullable=False,
                  server_default="medium"),
        sa.Column("details", JSONB, nullable=False, server_default="{}"),
        sa.Column("discovery_source", sa.String(64), nullable=False,
                  server_default="manual"),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_soc_ai_assets_kind_status",
        "soc_ai_assets", ["kind", "status"],
    )


def downgrade() -> None:
    op.drop_index("idx_soc_ai_assets_kind_status", table_name="soc_ai_assets")
    op.drop_table("soc_ai_assets")
    bind = op.get_bind()
    sa.Enum(name="ai_asset_risk").drop(bind, checkfirst=True)
    sa.Enum(name="ai_asset_status").drop(bind, checkfirst=True)
    sa.Enum(name="ai_asset_kind").drop(bind, checkfirst=True)
