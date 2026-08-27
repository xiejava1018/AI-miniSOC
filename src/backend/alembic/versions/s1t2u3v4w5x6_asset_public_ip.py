"""add soc_assets.public_ip for internet exposure scan

Revision ID: s1t2u3v4w5x6
Revises: r1s2t3u4v5w6
Create Date: 2026-08-26

- 新增列 public_ip（Text，可空）：云上资产的公网 IP（asset_ip 存的是内网 IP）
- 部分唯一索引 uq_soc_assets_public_ip（NULL 不受约束），防一 IP 挂多资产
- 数据回填示例（幂等，仅当资产名以公网 IP 结尾且该资产尚无 public_ip 时推断）：
  aliCloudECS-120.25.191.240-agent -> public_ip=120.25.191.240
  仅匹配非私网 IPv4，避免把内网 IP 误判为公网
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


def _text_col():
    return sa.Column("public_ip", sa.Text(), nullable=True)

revision: str = "s1t2u3v4w5x6"
down_revision: Union[str, Sequence[str], None] = "r1s2t3u4v5w6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "soc_assets",
        _text_col(),
    )
    # 部分唯一索引（NULL 不参与唯一约束）
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_soc_assets_public_ip "
        "ON soc_assets (public_ip) WHERE public_ip IS NOT NULL"
    )
    # 幂等回填：资产名形如 xxx-<IPv4>[-yyy]，且该 IPv4 为公网地址、资产当前无 public_ip
    op.execute("""
        UPDATE soc_assets a
        SET public_ip = (regexp_match(a.name, '-((\\d{1,3}\\.){3}\\d{1,3})'))[1]
        WHERE a.public_ip IS NULL
          AND a.name IS NOT NULL
          AND regexp_match(a.name, '-((\\d{1,3}\\.){3}\\d{1,3})') IS NOT NULL
          AND NOT ((regexp_match(a.name, '-((\\d{1,3}\\.){3}\\d{1,3})'))[1]::inet << '10.0.0.0/8'
                OR (regexp_match(a.name, '-((\\d{1,3}\\.){3}\\d{1,3})'))[1]::inet << '172.16.0.0/12'
                OR (regexp_match(a.name, '-((\\d{1,3}\\.){3}\\d{1,3})'))[1]::inet << '192.168.0.0/16'
                OR (regexp_match(a.name, '-((\\d{1,3}\\.){3}\\d{1,3})'))[1]::inet << '127.0.0.0/8')
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_soc_assets_public_ip")
    op.drop_column("soc_assets", "public_ip")
