"""asset_port_vulnerabilities

P4-B-α: soc_asset_ports 加 JSONB 列 vulnerabilities 存 vulners CVE 列表。

设计：
- 列与既有 vulnerability (Text) 并存；vulnerability 留作未来单条描述
- 默认空数组 '[]'::jsonb，旧行不受影响
- 安全幂等：IF NOT EXISTS（即使生产已手 ALTER 过也不冲突）

Revision ID: q1r2s3t4u5v6
Revises: p1q2r3s4t5u6
Create Date: 2026-08-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "q1r2s3t4u5v6"
down_revision: Union[str, Sequence[str], None] = "p1q2r3s4t5u6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE soc_asset_ports "
        "ADD COLUMN IF NOT EXISTS vulnerabilities JSONB "
        "NOT NULL DEFAULT '[]'::jsonb"
    )
    # 加 GIN 索引（方便后续按 CVE 反查哪些资产受影响：WHERE vulnerabilities @> '[\"CVE-...\"]'）
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_asset_ports_vulns_gin "
        "ON soc_asset_ports USING GIN (vulnerabilities)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_asset_ports_vulns_gin")
    op.execute("ALTER TABLE soc_asset_ports DROP COLUMN IF EXISTS vulnerabilities")
