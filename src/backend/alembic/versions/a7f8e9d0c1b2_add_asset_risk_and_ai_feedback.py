"""add asset risk scoring + ai feedback (P3/F1.1+F4.1)

Revision ID: a7f8e9d0c1b2
Revises: a0b1c2d3e4f5
Create Date: 2026-08-21 10:00:00.000000

P3 MVP（PRD ai-asset-management-prd.md v1.2.1）：
- soc_assets 扩 4 列：risk_score / risk_summary / risk_scored_at / score_breakdown
  （risk_score 可空：NULL = 未评分或数据全缺失 N/A，不误导为 0 分）
- 新表 soc_asset_risk_history：评分历史快照（趋势折线 / 评分上升检测）
- 新表 soc_ai_feedback：AI 产物 👍/👎 反馈（F4.1 反馈闭环）

注：user_id 用 INTEGER 对齐 soc_users.id（PRD 草案写 UUID，实现时对齐现实 schema）。
全部幂等（IF NOT EXISTS），支持在已手工建列的库上重跑。
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a7f8e9d0c1b2'
down_revision: Union[str, Sequence[str], None] = 'a0b1c2d3e4f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- 1. soc_assets 扩列（幂等） ----
    op.execute("ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS risk_score INTEGER")
    op.execute("ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS risk_summary TEXT")
    op.execute("ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS risk_scored_at TIMESTAMPTZ")
    op.execute("ALTER TABLE soc_assets ADD COLUMN IF NOT EXISTS score_breakdown JSONB")
    # 列表页风险列排序
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_soc_assets_risk_score
        ON soc_assets (risk_score DESC NULLS LAST)
    """)

    # ---- 2. 风险评分历史表 ----
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_asset_risk_history (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            asset_id UUID NOT NULL REFERENCES soc_assets(id) ON DELETE CASCADE,
            risk_score INTEGER NOT NULL,
            score_breakdown JSONB,
            scored_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_soc_asset_risk_history_asset_time
        ON soc_asset_risk_history (asset_id, scored_at)
    """)

    # ---- 3. AI 反馈表 ----
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_ai_feedback (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            target_type VARCHAR(50) NOT NULL,
            target_id VARCHAR(100) NOT NULL,
            rating VARCHAR(10) NOT NULL,
            comment TEXT,
            user_id INTEGER REFERENCES soc_users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_soc_ai_feedback_target
        ON soc_ai_feedback (target_type, target_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_soc_ai_feedback_created
        ON soc_ai_feedback (created_at)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS soc_ai_feedback CASCADE")
    op.execute("DROP TABLE IF EXISTS soc_asset_risk_history CASCADE")
    op.execute("DROP INDEX IF EXISTS idx_soc_assets_risk_score")
    op.execute("ALTER TABLE soc_assets DROP COLUMN IF EXISTS score_breakdown")
    op.execute("ALTER TABLE soc_assets DROP COLUMN IF EXISTS risk_scored_at")
    op.execute("ALTER TABLE soc_assets DROP COLUMN IF EXISTS risk_summary")
    op.execute("ALTER TABLE soc_assets DROP COLUMN IF EXISTS risk_score")
