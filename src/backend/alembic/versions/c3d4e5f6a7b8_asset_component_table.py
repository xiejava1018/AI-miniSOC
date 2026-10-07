"""OH-1.4 方案3：资产组件表（SBOM 物化）

soc_asset_components：syscollector packages 物化落表，
对应本体 asset-component（SBOM 级组件，用于漏洞匹配与降误报）。
数据由 asset_component_sync 全量刷新（按 asset 先删后插）。

Revision ID: c3d4e5f6a7b8
Revises: u7v8w9x0y1z2
Create Date: 2026-10-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "u7v8w9x0y1z2"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None


def upgrade() -> None:
    op.create_table(
        "soc_asset_components",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("asset_id", UUID(as_uuid=True),
                  sa.ForeignKey("soc_assets.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("agent_id", sa.String(64), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("component_type", sa.String(32), nullable=False,
                  server_default="other"),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("path", sa.Text(), nullable=True),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.UniqueConstraint("asset_id", "name", "version", "component_type",
                            name="uq_asset_component"),
    )


def downgrade() -> None:
    op.drop_table("soc_asset_components")
