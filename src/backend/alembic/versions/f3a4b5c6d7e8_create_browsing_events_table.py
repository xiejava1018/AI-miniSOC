"""create browsing events table (P1-T2 + P1-T4 base)

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-08-16 21:30:00.000000

P1-T2：把 soc_browsing_events 从运行时 create_all 迁移化。
P1-T4：基础表结构（唯一约束在 f4a5b6c7d8e9 中加）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f3a4b5c6d7e8'
down_revision: Union[str, Sequence[str], None] = 'e2f3a4b5c6d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create soc_browsing_events table idempotently."""
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_browsing_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ip VARCHAR(45) NOT NULL,
            domain VARCHAR(500) NOT NULL,
            apptype VARCHAR(50),
            score INTEGER NOT NULL,
            severity VARCHAR(20) NOT NULL,
            rule_hits JSONB NOT NULL,
            source_count INTEGER NOT NULL DEFAULT 0,
            window_start TIMESTAMPTZ NOT NULL,
            window_end TIMESTAMPTZ NOT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'new',
            incident_id UUID,
            ai_analysis_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            resolved_at TIMESTAMPTZ,
            resolution_note TEXT
        )
    """)
    # 索引（幂等）
    op.execute("CREATE INDEX IF NOT EXISTS ix_browsing_events_ip_domain ON soc_browsing_events (ip, domain)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_soc_browsing_events_ip ON soc_browsing_events (ip)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_soc_browsing_events_domain ON soc_browsing_events (domain)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_browsing_events_created ON soc_browsing_events (created_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_browsing_events_status ON soc_browsing_events (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_soc_browsing_events_incident_id ON soc_browsing_events (incident_id)")


def downgrade() -> None:
    """Drop soc_browsing_events table."""
    op.execute("DROP TABLE IF EXISTS soc_browsing_events CASCADE")