"""add soc_browsing_events unique constraint (P1-T4)

Revision ID: a4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-08-16 22:00:00.000000

P1-T4：行为事件幂等落库

为 soc_browsing_events 添加唯一约束 (ip, domain, window_start, window_end)，
确保同一窗口的同一 (ip, domain) 不重复落库。

迁移先清理存量重复（每组保留 created_at 最小的那条），再加约束。

事件服务改 INSERT ... ON CONFLICT DO NOTHING（见 event_service.py 修改）。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a4b5c6d7e8f9'
down_revision: Union[str, Sequence[str], None] = 'f3a4b5c6d7e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """清理存量重复并加唯一约束。"""
    # 1. 清重复：保留 id 最小（即最早创建的）那一条，删其余
    op.execute("""
        DELETE FROM soc_browsing_events
        WHERE id NOT IN (
            SELECT min_id FROM (
                SELECT MIN(id::text)::uuid AS min_id
                FROM soc_browsing_events
                GROUP BY ip, domain, window_start, window_end
            ) AS keepers
        )
    """)

    # 2. 加唯一约束
    op.create_unique_constraint(
        "uq_browsing_event_window",
        "soc_browsing_events",
        ["ip", "domain", "window_start", "window_end"],
    )


def downgrade() -> None:
    """删除唯一约束（不还原已删除的重复行）。"""
    op.drop_constraint("uq_browsing_event_window", "soc_browsing_events", type_="unique")