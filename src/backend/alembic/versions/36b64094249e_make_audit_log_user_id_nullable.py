"""make_audit_log_user_id_nullable

Revision ID: 36b64094249e
Revises: c5962ab1f662
Create Date: 2026-03-24 17:20:17.579176

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36b64094249e'
down_revision: Union[str, Sequence[str], None] = 'c5962ab1f662'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 先删除旧的外键约束
    op.execute("ALTER TABLE soc_audit_logs DROP CONSTRAINT IF EXISTS soc_audit_logs_user_id_fkey")
    # 修改列可为空
    op.alter_column('soc_audit_logs', 'user_id',
                    existing_type=sa.BigInteger(),
                    nullable=True)
    # 重新创建带 ON DELETE SET NULL 的外键约束
    op.create_foreign_key(
        'soc_audit_logs_user_id_fkey',
        'soc_audit_logs', 'soc_users',
        ['user_id'], ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    """Downgrade schema."""
    # 删除外键约束
    op.execute("ALTER TABLE soc_audit_logs DROP CONSTRAINT IF EXISTS soc_audit_logs_user_id_fkey")
    # 修改列为不可空
    op.alter_column('soc_audit_logs', 'user_id',
                    existing_type=sa.BigInteger(),
                    nullable=False)
    # 重新创建不带 ON DELETE 的外键约束
    op.create_foreign_key(
        'soc_audit_logs_user_id_fkey',
        'soc_audit_logs', 'soc_users',
        ['user_id'], ['id']
    )
