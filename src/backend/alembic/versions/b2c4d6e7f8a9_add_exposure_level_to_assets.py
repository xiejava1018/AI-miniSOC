"""add_exposure_level_to_assets

Revision ID: b2c4d6e7f8a9
Revises: a1b2c3d4e5f6
Create Date: 2026-03-25 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c4d6e7f8a9'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 添加exposure_level字段到soc_assets表
    op.add_column(
        'soc_assets',
        sa.Column('exposure_level', sa.String(20), nullable=True, server_default='internal')
    )

    # 创建索引
    op.create_index('idx_soc_assets_exposure_level', 'soc_assets', ['exposure_level'])

    # 更新现有数据的默认值
    op.execute("""
        UPDATE soc_assets
        SET exposure_level = 'internal'
        WHERE exposure_level IS NULL;
    """)

    # 设置为NOT NULL
    op.alter_column(
        'soc_assets',
        'exposure_level',
        existing_type=sa.String(20),
        nullable=False
    )


def downgrade() -> None:
    """Downgrade schema."""

    # 删除索引
    op.drop_index('idx_soc_assets_exposure_level', 'soc_assets')

    # 删除字段
    op.drop_column('soc_assets', 'exposure_level')
