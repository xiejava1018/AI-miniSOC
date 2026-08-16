"""add_sca_tables

Revision ID: c3d4e5f6g7h8
Revises: b2c4d6e7f8a9
Create Date: 2026-03-25 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
# P4：原 down_revision=a1b2c3d4e5f6，与 b2c4d6e7f8a9 形成分叉。
# 改为 b2c4d6e7f8a9 以形成单链：a1b2c3d4e5f6 → b2c4d6e7f8a9 → c3d4e5f6g7h8 → a1b2c3d4e5f7
revision: str = 'c3d4e5f6g7h8'
down_revision: Union[str, Sequence[str], None] = 'b2c4d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    # 创建SCA检查项定义表
    op.create_table(
        'soc_sca_checks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('check_id', sa.Integer(), nullable=False),
        sa.Column('policy_id', sa.String(100), nullable=False),
        sa.Column('title', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('remediation', sa.Text(), nullable=True),
        sa.Column('compliance', postgresql.JSONB(), nullable=True),
        sa.Column('rules', postgresql.JSONB(), nullable=True),
        sa.Column('condition', sa.String(20), nullable=True),
        sa.Column('command', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )

    # 创建唯一约束
    op.create_unique_constraint('uq_sca_check_policy', 'soc_sca_checks', ['check_id', 'policy_id'])

    # 创建SCA检查项表索引
    op.create_index('idx_soc_sca_checks_check_id', 'soc_sca_checks', ['check_id'])
    op.create_index('idx_soc_sca_checks_policy_id', 'soc_sca_checks', ['policy_id'])

    # 创建资产SCA检查结果表
    op.create_table(
        'soc_asset_sca_checks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('asset_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sca_check_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('result', sa.String(20), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='open'),
        sa.Column('last_scan_time', sa.DateTime(timezone=True), nullable=False),
        sa.Column('scan_score', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('NOW()')),
    )

    # 创建唯一约束
    op.create_unique_constraint('uq_asset_sca_check', 'soc_asset_sca_checks', ['asset_id', 'sca_check_id'])

    # 创建外键约束（P4：使用 op.execute 原生 SQL 避开 SQLAlchemy 2.0 与 alembic 1.19 的 Table 构造兼容性问题）
    op.execute("""
        ALTER TABLE soc_asset_sca_checks
        ADD CONSTRAINT fk_asset_sca_checks_asset_id
        FOREIGN KEY (asset_id) REFERENCES soc_assets(id) ON DELETE CASCADE
    """)
    op.execute("""
        ALTER TABLE soc_asset_sca_checks
        ADD CONSTRAINT fk_asset_sca_checks_sca_check_id
        FOREIGN KEY (sca_check_id) REFERENCES soc_sca_checks(id) ON DELETE CASCADE
    """)

    # 创建资产SCA检查结果表索引
    op.create_index('idx_soc_asset_sca_checks_asset_id', 'soc_asset_sca_checks', ['asset_id'])
    op.create_index('idx_soc_asset_sca_checks_sca_check_id', 'soc_asset_sca_checks', ['sca_check_id'])
    op.create_index('idx_soc_asset_sca_checks_result', 'soc_asset_sca_checks', ['result'])
    op.create_index('idx_soc_asset_sca_checks_last_scan_time', 'soc_asset_sca_checks', ['last_scan_time'])


def downgrade() -> None:
    """Downgrade schema."""

    # 删除资产SCA检查结果表
    op.drop_index('idx_soc_asset_sca_checks_last_scan_time', table_name='soc_asset_sca_checks')
    op.drop_index('idx_soc_asset_sca_checks_result', table_name='soc_asset_sca_checks')
    op.drop_index('idx_soc_asset_sca_checks_sca_check_id', table_name='soc_asset_sca_checks')
    op.drop_index('idx_soc_asset_sca_checks_asset_id', table_name='soc_asset_sca_checks')
    op.drop_constraint('fk_asset_sca_checks_sca_check_id', table_name='soc_asset_sca_checks')
    op.drop_constraint('fk_asset_sca_checks_asset_id', table_name='soc_asset_sca_checks')
    op.drop_constraint('uq_asset_sca_check', table_name='soc_asset_sca_checks')
    op.drop_table('soc_asset_sca_checks')

    # 删除SCA检查项定义表
    op.drop_index('idx_soc_sca_checks_policy_id', table_name='soc_sca_checks')
    op.drop_index('idx_soc_sca_checks_check_id', table_name='soc_sca_checks')
    op.drop_constraint('uq_sca_check_policy', table_name='soc_sca_checks')
    op.drop_table('soc_sca_checks')
