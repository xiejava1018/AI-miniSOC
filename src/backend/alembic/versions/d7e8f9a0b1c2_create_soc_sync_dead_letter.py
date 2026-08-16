"""create soc_sync_dead_letter table (P2-T4)

Revision ID: d7e8f9a0b1c2
Revises: c6d7e8f9a0b1
Create Date: 2026-08-17 00:00:00.000000

P2-T4：同步失败可追踪/重放

同步批次级错误明细与死信队列表：
- batch_id：同一批推送的 items 共用一个 batch_id（UUID）
- error_class / error_message：错误类型与消息
- raw_item：失败时该 item 的 JSON 原文（支持重放）
- replay_count / last_replayed_at：重放次数与时间
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd7e8f9a0b1c2'
down_revision: Union[str, Sequence[str], None] = 'c6d7e8f9a0b1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create soc_sync_dead_letter idempotently."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_sync_dead_letter (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            batch_id UUID NOT NULL,
            source VARCHAR(100) NOT NULL,
            data_type VARCHAR(50) NOT NULL,
            item_index INTEGER NOT NULL,
            item_key VARCHAR(255),
            error_class VARCHAR(100),
            error_message TEXT,
            raw_item JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            replay_count INTEGER NOT NULL DEFAULT 0,
            last_replayed_at TIMESTAMPTZ,
            resolved BOOLEAN NOT NULL DEFAULT false
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_soc_sync_dl_batch ON soc_sync_dead_letter (batch_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_soc_sync_dl_source ON soc_sync_dead_letter (source)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_soc_sync_dl_resolved ON soc_sync_dead_letter (resolved, created_at)")


def downgrade() -> None:
    """Drop soc_sync_dead_letter."""
    op.execute("DROP TABLE IF EXISTS soc_sync_dead_letter CASCADE")