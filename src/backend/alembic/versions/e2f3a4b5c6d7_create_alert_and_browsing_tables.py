"""create alert and browsing tables (P1-T2)

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-08-16 21:00:00.000000

P1-T2：把运行时 Base.metadata.create_all() 迁移化。

原代码位置：
- app/services/alert_group_snapshot_service.py:45（soc_alert_groups + soc_alert_group_analyses）
- app/services/alert_group_snapshot_scheduler.py:32（soc_alert_groups）
- app/services/alert_digest_service.py:37（soc_alert_digests + soc_alert_group_analyses）
- app/services/alert_group_triage_service.py:42（soc_alert_group_analyses）
- app/services/browsing_detection/scheduler.py:46（soc_browsing_* 三张）

所有表已在生产库存在（实测 2026-08-16，34 张 soc_ 表齐备），
此迁移使用 IF NOT EXISTS 语义，对新老库都安全。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create alert and browsing tables idempotently."""

    # === soc_alert_digests ===
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_alert_digests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            period_type VARCHAR(10) NOT NULL,
            period_start TIMESTAMPTZ,
            period_end TIMESTAMPTZ,
            total_alerts INTEGER,
            by_level JSONB,
            top_groups JSONB,
            top_assets JSONB,
            trend JSONB,
            summary_text TEXT,
            ai_model VARCHAR(50),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)

    # === soc_alert_group_analyses ===
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_alert_group_analyses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            fingerprint VARCHAR(255) NOT NULL,
            priority VARCHAR(4),
            is_noise BOOLEAN,
            suggest_incident BOOLEAN,
            verdict_at TIMESTAMPTZ,
            ai_model VARCHAR(50),
            explanation TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_soc_alert_group_analyses_fingerprint ON soc_alert_group_analyses (fingerprint)")

    # === soc_browsing_baseline ===
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_browsing_baseline (
            id BIGSERIAL PRIMARY KEY,
            ip VARCHAR(45) NOT NULL,
            domain VARCHAR(500) NOT NULL,
            first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
            total_count BIGINT NOT NULL DEFAULT 1,
            CONSTRAINT uq_browsing_baseline_ip_domain UNIQUE (ip, domain)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_browsing_baseline_ip ON soc_browsing_baseline (ip)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_browsing_baseline_last_seen ON soc_browsing_baseline (last_seen)")

    # === soc_browsing_blacklist ===
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_browsing_blacklist (
            id BIGSERIAL PRIMARY KEY,
            domain VARCHAR(255) NOT NULL UNIQUE,
            source VARCHAR(50) NOT NULL DEFAULT 'manual',
            reason VARCHAR(255),
            created_by BIGINT REFERENCES soc_users(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_soc_browsing_blacklist_domain ON soc_browsing_blacklist (domain)")


def downgrade() -> None:
    """Drop tables (cascading risk: do not use in production)."""
    op.execute("DROP TABLE IF EXISTS soc_browsing_blacklist CASCADE")
    op.execute("DROP TABLE IF EXISTS soc_browsing_baseline CASCADE")
    op.execute("DROP TABLE IF EXISTS soc_alert_group_analyses CASCADE")
    op.execute("DROP TABLE IF EXISTS soc_alert_digests CASCADE")