"""add_asset_network_zone

Revision ID: 807124bfc2bc
Revises: 36b64094249e
Create Date: 2026-06-02 20:39:08.943531

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '807124bfc2bc'
down_revision: Union[str, Sequence[str], None] = '36b64094249e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 添加 network_zone 列，默认值 'other'（先设默认值让历史行自动填上）
    op.add_column(
        'soc_assets',
        sa.Column('network_zone', sa.String(length=50), nullable=False, server_default='other')
    )

    # 2. 添加 CHECK 约束（5 个网络区域枚举值）
    op.execute("""
        ALTER TABLE soc_assets
        ADD CONSTRAINT soc_assets_network_zone_check
        CHECK (network_zone IN ('intranet', 'dmz', 'office', 'management', 'other'))
    """)

    # 3. 添加索引（用于按网络区域筛选）
    op.create_index(
        'idx_soc_assets_network_zone',
        'soc_assets',
        ['network_zone']
    )

    # 4. 添加字段注释
    op.execute("COMMENT ON COLUMN soc_assets.network_zone IS '网络区域（intranet/dmz/office/management/other）'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('idx_soc_assets_network_zone', table_name='soc_assets')
    op.execute("ALTER TABLE soc_assets DROP CONSTRAINT IF EXISTS soc_assets_network_zone_check")
    op.drop_column('soc_assets', 'network_zone')
