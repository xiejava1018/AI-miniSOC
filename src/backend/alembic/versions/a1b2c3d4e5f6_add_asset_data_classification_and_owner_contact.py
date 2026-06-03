"""add_asset_data_classification_and_owner_contact

Revision ID: a1b2c3d4e5f6
Revises: 807124bfc2bc
Create Date: 2026-06-03 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '807124bfc2bc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. 添加 data_classification 列，默认值 'internal'（先设默认值让历史行自动填上）
    op.add_column(
        'soc_assets',
        sa.Column('data_classification', sa.String(length=20), nullable=False, server_default='internal')
    )

    # 2. 添加 CHECK 约束（4 个数据分类枚举值）
    op.execute("""
        ALTER TABLE soc_assets
        ADD CONSTRAINT soc_assets_data_classification_check
        CHECK (data_classification IN ('public', 'internal', 'confidential', 'secret'))
    """)

    # 3. 添加字段注释
    op.execute("COMMENT ON COLUMN soc_assets.data_classification IS '数据敏感度（public/internal/confidential/secret）'")

    # 4. 添加 owner_contact 列（可空，无默认值）
    op.add_column(
        'soc_assets',
        sa.Column('owner_contact', sa.String(length=50), nullable=True)
    )

    # 5. 字段注释
    op.execute("COMMENT ON COLUMN soc_assets.owner_contact IS '负责人联系电话'")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('soc_assets', 'owner_contact')
    op.execute("ALTER TABLE soc_assets DROP CONSTRAINT IF EXISTS soc_assets_data_classification_check")
    op.drop_column('soc_assets', 'data_classification')
