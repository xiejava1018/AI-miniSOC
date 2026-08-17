"""drop circular FK fk_task_registry_current_run (task observability v0.4.2)

Revision ID: f9a0b1c2d3e4
Revises: e8f9a0b1c2d3
Create Date: 2026-08-16 23:15:00.000000

soc_task_registry.current_run_id 和 soc_task_runs.task_key 形成循环 FK，
SQLAlchemy create_all/drop_all 拓扑排序失败。
current_run_id 只是个指针，不需要 DB FK 约束，应用层保证有效。
"""
from typing import Sequence, Union

from alembic import op

revision: str = "f9a0b1c2d3e4"
down_revision: Union[str, Sequence[str], None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE soc_task_registry "
        "DROP CONSTRAINT IF EXISTS fk_task_registry_current_run"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE soc_task_registry "
        "ADD CONSTRAINT fk_task_registry_current_run "
        "FOREIGN KEY (current_run_id) REFERENCES soc_task_runs(id) ON DELETE SET NULL"
    )
