"""add soc_browsing_events foreign keys (P2-T2)

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-08-16 23:00:00.000000

P2-T2：为 soc_browsing_events 加外键约束 incident_id → soc_incidents(id) 和
ai_analysis_id → soc_ai_analyses(id)，ON DELETE SET NULL。

清理孤儿引用后加约束（实测 2026-08-16 当前库 0 孤儿）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5c6d7e8f9a0'
down_revision: Union[str, Sequence[str], None] = 'a4b5c6d7e8f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Clean orphans then add FK with ON DELETE SET NULL."""
    # 1. 清孤儿引用（清零）
    op.execute("""
        UPDATE soc_browsing_events
        SET incident_id = NULL
        WHERE incident_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM soc_incidents WHERE id = soc_browsing_events.incident_id)
    """)
    op.execute("""
        UPDATE soc_browsing_events
        SET ai_analysis_id = NULL
        WHERE ai_analysis_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM soc_ai_analyses WHERE id = soc_browsing_events.ai_analysis_id)
    """)

    # 2. 加 FK（先看是否已存在，避免重复添加报错）
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_browsing_events_incident'
            ) THEN
                ALTER TABLE soc_browsing_events
                ADD CONSTRAINT fk_browsing_events_incident
                FOREIGN KEY (incident_id) REFERENCES soc_incidents(id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_browsing_events_ai_analysis'
            ) THEN
                ALTER TABLE soc_browsing_events
                ADD CONSTRAINT fk_browsing_events_ai_analysis
                FOREIGN KEY (ai_analysis_id) REFERENCES soc_ai_analyses(id) ON DELETE SET NULL;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    """Remove FK constraints."""
    op.execute("ALTER TABLE soc_browsing_events DROP CONSTRAINT IF EXISTS fk_browsing_events_ai_analysis")
    op.execute("ALTER TABLE soc_browsing_events DROP CONSTRAINT IF EXISTS fk_browsing_events_incident")