"""behavior profile tables (P1.5)

快照/域名明细/水位三张表（docs/design/2026-09-05-用户IP行为画像-方案设计.md §9.2）。
建表用 Base.metadata 局部 CreateTable(if_not_exists)，与 ORM 永远一致，避免第三份 schema 漂移。
幂等：IF NOT EXISTS + NOT EXISTS 插水位行。

Revision ID: x3y4z5a6b7c8
Revises: w2x3y4z5a6b7
Create Date: 2026-09-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.base import Base
import app.models  # noqa: F401  触发全部 model 注册

# revision identifiers, used by Alembic.
revision: str = "x3y4z5a6b7c8"
down_revision: Union[str, Sequence[str], None] = "w2x3y4z5a6b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("soc_behavior_profiles", "soc_behavior_domains", "soc_behavior_profile_watermark")


def upgrade() -> None:
    # 1) 建表（幂等）
    for t in _TABLES:
        op.execute(
            str(CreateTable(Base.metadata.tables[t], if_not_exists=True)
                .compile(dialect=postgresql.dialect()))
            .replace("COMMIT", "")  # CreateTable 编译可能带 DDL 事务串，去掉
        )

    # 2) 水位行（幂等：NOT EXISTS）
    bind = op.get_bind()
    bind.execute(sa.text(
        "INSERT INTO soc_behavior_profile_watermark (id, last_completed_date) "
        "SELECT 1, NULL WHERE NOT EXISTS (SELECT 1 FROM soc_behavior_profile_watermark WHERE id = 1)"
    ))


def downgrade() -> None:
    # 先子后父（soc_behavior_profiles/domains 的 FK 指向 soc_assets，无互相依赖；
    # 但保持确定性顺序：domains → profiles → watermark）
    op.execute("DROP TABLE IF EXISTS soc_behavior_domains")
    op.execute("DROP TABLE IF EXISTS soc_behavior_profiles")
    op.execute("DROP TABLE IF EXISTS soc_behavior_profile_watermark")
