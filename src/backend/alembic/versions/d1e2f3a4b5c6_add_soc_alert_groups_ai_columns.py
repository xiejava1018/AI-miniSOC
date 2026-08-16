"""add soc_alert_groups ai columns (P1-T2)

Revision ID: d1e2f3a4b5c6
Revises: a1b2c3d4e5f7
Create Date: 2026-08-16 20:30:00.000000

P1-T2：把运行时 ALTER TABLE ... ADD COLUMN IF NOT EXISTS ... 迁移化。

原代码位置：app/services/alert_group_snapshot_service.py:58
原代码：
    for col, typ in (
        ("ai_priority", "VARCHAR(4)"),
        ("ai_is_noise", "BOOLEAN"),
        ("ai_suggest_incident", "BOOLEAN"),
        ("ai_verdict_at", "TIMESTAMPTZ"),
    ):
        self.db.execute(
            text(f"ALTER TABLE soc_alert_groups ADD COLUMN IF NOT EXISTS {col} {typ}")
        )

注：列已在生产库存在（实测 2026-08-16，\d soc_alert_groups 可见 22 列含全部 AI 列），
此迁移在 IF NOT EXISTS 语义下对新库和老库都安全。模型 AlertGroupSnapshot 已声明对应字段。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add AI verdict columns to soc_alert_groups (idempotent).

    soc_alert_groups 表本身由 alert_group_snapshot 模型定义（含在 Base.metadata），
    新库初始化时需先 create_all 建表（alembic 当前不在 env.py 中 autogenerate，
    故仅依赖 IF NOT EXISTS 列加），老库已是 CREATE TABLE 后的 ALTER。
    """
    # 确保表存在（新库首次迁移时）
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_alert_groups (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            snapshot_at TIMESTAMPTZ NOT NULL,
            window_hours INTEGER NOT NULL DEFAULT 24,
            fingerprint VARCHAR(255) NOT NULL,
            rule_id VARCHAR(64),
            rule_description TEXT,
            agent_id VARCHAR(64),
            agent_name VARCHAR(255),
            agent_ip TEXT,
            count INTEGER NOT NULL DEFAULT 0,
            level_min INTEGER,
            level_max INTEGER,
            first_seen TEXT,
            last_seen TEXT,
            distinct_srcips INTEGER,
            top_srcips JSONB,
            linked_asset_id UUID REFERENCES soc_assets(id),
            ai_priority VARCHAR(4),
            ai_is_noise BOOLEAN,
            ai_suggest_incident BOOLEAN,
            ai_verdict_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    # 老库 ALTER 列（已存在则跳过）
    op.execute("ALTER TABLE soc_alert_groups ADD COLUMN IF NOT EXISTS ai_priority VARCHAR(4)")
    op.execute("ALTER TABLE soc_alert_groups ADD COLUMN IF NOT EXISTS ai_is_noise BOOLEAN")
    op.execute("ALTER TABLE soc_alert_groups ADD COLUMN IF NOT EXISTS ai_suggest_incident BOOLEAN")
    op.execute("ALTER TABLE soc_alert_groups ADD COLUMN IF NOT EXISTS ai_verdict_at TIMESTAMPTZ")
    # 索引（幂等）
    op.execute("CREATE INDEX IF NOT EXISTS ix_soc_alert_groups_snapshot_at ON soc_alert_groups (snapshot_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_soc_alert_groups_fingerprint ON soc_alert_groups (fingerprint)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_soc_alert_groups_agent_ip ON soc_alert_groups (agent_ip)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_soc_alert_groups_linked_asset_id ON soc_alert_groups (linked_asset_id)")


def downgrade() -> None:
    """Drop AI verdict columns from soc_alert_groups."""
    op.execute("ALTER TABLE soc_alert_groups DROP COLUMN IF EXISTS ai_verdict_at")
    op.execute("ALTER TABLE soc_alert_groups DROP COLUMN IF EXISTS ai_suggest_incident")
    op.execute("ALTER TABLE soc_alert_groups DROP COLUMN IF EXISTS ai_is_noise")
    op.execute("ALTER TABLE soc_alert_groups DROP COLUMN IF EXISTS ai_priority")