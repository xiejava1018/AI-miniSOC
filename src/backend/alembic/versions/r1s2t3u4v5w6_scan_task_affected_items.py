"""scan_task_affected_items

P3/F-S3 增强：soc_scanner_tasks 加 affected_ports / affected_findings JSONB 列，
记录本次扫描具体动了哪些端口/发现，便于任务详情页直接展示明细
（之前只能看「扫 X / 新 Y / 更 Z / 败 W」总数，要看具体哪几条得跳资产或回溯 last_seen）。

设计：
- affected_ports:    [{"id": uuid, "ip": "...", "port": int, "protocol": "tcp|udp",
                      "action": "created"|"updated", "service": "...", "version": "..."}]
- affected_findings: [{"id": int, "ip": "...", "mac": "...", "action": "...",
                      "matched_asset_id": uuid|null}]
- 默认 '[]'::jsonb，旧行不受影响（历史任务回查为空，前端要降级显示）
- 幂等：IF NOT EXISTS

Revision ID: r1s2t3u4v5w6
Revises: q1r2s3t4u5v6
Create Date: 2026-08-27
"""
from typing import Sequence, Union

from alembic import op


revision: str = "r1s2t3u4v5w6"
down_revision: Union[str, Sequence[str], None] = "q1r2s3t4u5v6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE soc_scanner_tasks "
        "ADD COLUMN IF NOT EXISTS affected_ports JSONB "
        "NOT NULL DEFAULT '[]'::jsonb"
    )
    op.execute(
        "ALTER TABLE soc_scanner_tasks "
        "ADD COLUMN IF NOT EXISTS affected_findings JSONB "
        "NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE soc_scanner_tasks DROP COLUMN IF EXISTS affected_findings")
    op.execute("ALTER TABLE soc_scanner_tasks DROP COLUMN IF EXISTS affected_ports")