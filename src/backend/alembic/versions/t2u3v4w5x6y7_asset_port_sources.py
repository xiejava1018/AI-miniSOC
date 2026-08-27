"""soc_asset_ports multi-source fusion columns + backfill

Revision ID: t2u3v4w5x6y7
Revises: s1t2u3v4w5x6
Create Date: 2026-08-27

方案 A（一端口一行，字段级多源融合）：
- 新列 sources JSONB DEFAULT '[]'：观测来源清单
- 新列 last_seen_by_source JSONB DEFAULT '{}'：每来源各自最后观测时间
- 回填：既有行 sources 按 asset_id 是否挂到资产推断
  （挂了 = 手工登记 'manual'，未挂 = 扫描器 'scanner'）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "t2u3v4w5x6y7"
down_revision: Union[str, Sequence[str], None] = "s1t2u3v4w5x6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("soc_asset_ports", sa.Column("sources", JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=True))
    op.add_column("soc_asset_ports", sa.Column("last_seen_by_source", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=True))
    # 幂等回填：既有行统一标 'scanner'。
    # 不用「asset_id 非空猜 manual」——扫描器创建且 IP 命中台账的行也带 asset_id，
    # 无法区分；而端口数据事实上几乎全部来自扫描同步（19265fdd 教训：误标 manual 误导用户）。
    # 后续新增的 manual 录入走融合路径会正确标注。
    op.execute("""
        UPDATE soc_asset_ports
        SET sources = '["scanner"]'::jsonb
        WHERE sources = '[]'::jsonb
    """)
    op.execute("""
        UPDATE soc_asset_ports
        SET last_seen_by_source = jsonb_build_object('scanner', COALESCE(last_seen, scan_time))
        WHERE last_seen_by_source = '{}'::jsonb
    """)


def downgrade() -> None:
    op.drop_column("soc_asset_ports", "last_seen_by_source")
    op.drop_column("soc_asset_ports", "sources")
