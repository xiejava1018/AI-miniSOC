"""身份管道表（Phase 0，方案 §4.1）

Revision ID: a6b7c8d9e0f1
Revises: z5a6b7c8d9e0
Create Date: 2026-09-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.models.base import Base
import app.models  # noqa: F401

revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, Sequence[str], None] = "z5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("soc_identity_events", "soc_identity_bindings")


def upgrade() -> None:
    for t in _TABLES:
        op.execute(
            str(CreateTable(Base.metadata.tables[t], if_not_exists=True)
                .compile(dialect=postgresql.dialect())).replace("COMMIT", "")
        )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DROP TABLE IF EXISTS soc_identity_events"))
    bind.execute(sa.text("DROP TABLE IF EXISTS soc_identity_bindings"))
