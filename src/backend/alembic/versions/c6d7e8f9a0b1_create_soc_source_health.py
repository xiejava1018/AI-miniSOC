"""create soc_source_health table (P2-T3)

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-08-16 23:30:00.000000

P2-T3：数据源健康采集表。

各采集器/同步任务在执行成功/失败时更新 last_success_at / last_failure_at / failure_count，
仪表板据此计算"数据截至"并区分"正常 7 天窗口"vs"采集中断"。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6d7e8f9a0b1'
down_revision: Union[str, Sequence[str], None] = 'b5c6d7e8f9a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create soc_source_health idempotently."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_source_health (
            source_key VARCHAR(100) PRIMARY KEY,
            source_type VARCHAR(50) NOT NULL,
            display_name VARCHAR(200),
            last_success_at TIMESTAMPTZ,
            last_failure_at TIMESTAMPTZ,
            last_failure_message TEXT,
            success_count BIGINT NOT NULL DEFAULT 0,
            failure_count BIGINT NOT NULL DEFAULT 0,
            expected_interval_seconds INTEGER,
            last_records_count INTEGER,
            notes TEXT,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_soc_source_health_source_type
        ON soc_source_health (source_type)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_soc_source_health_last_success
        ON soc_source_health (last_success_at)
    """)


def downgrade() -> None:
    """Drop soc_source_health."""
    op.execute("DROP TABLE IF EXISTS soc_source_health CASCADE")