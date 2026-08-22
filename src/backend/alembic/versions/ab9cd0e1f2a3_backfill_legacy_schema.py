"""历史欠账补齐：7 张手工建表 + 7 个手工加列（§5.5 空库重建修复）

Revision ID: ab9cd0e1f2a3
Revises: f9a0b1c2d3e4
Create Date: 2026-08-22

背景：以下表/列在生产库是手工建的，从未进迁移链，导致空库
`alembic upgrade head` 在 a0b1c2d3e4f5（写 soc_role_menus.permissions）必挂。
本迁移插在断点之前，全部幂等（create_all checkfirst + ADD COLUMN IF NOT EXISTS）：

表（7）：soc_departments / soc_dicts / soc_notifications / soc_asset_sources /
         soc_chat_sessions / soc_chat_messages / soc_cisa_kev
列（7）：soc_role_menus.permissions（JSONB）
         soc_roles.is_active（BOOLEAN）
         soc_users.nick_name / phone / avatar / gender / department_id

注意：
- 建表用 Base.metadata 局部 create_all（checkfirst=True），保证与 ORM 定义
  永远一致，避免第三份 schema 漂移。
- 本迁移对生产无操作（列已存在、表已存在），幂等零副作用。
"""
from alembic import op
import sqlalchemy as sa

revision = "ab9cd0e1f2a3"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None

# 仅建这 7 张（其余表由链内既有迁移负责）
_TABLES_TO_CREATE = [
    "soc_departments", "soc_dicts", "soc_notifications", "soc_asset_sources",
    "soc_chat_sessions", "soc_chat_messages", "soc_cisa_kev",
]


def upgrade() -> None:
    # 1) 建表：从 Base.metadata 取这 7 张的权威定义
    from app.models.base import Base
    import app.models  # noqa: F401 注册全部模型
    from sqlalchemy.schema import CreateTable
    for tname in _TABLES_TO_CREATE:
        table = Base.metadata.tables[tname]
        op.execute(CreateTable(table, if_not_exists=True))

    # 2) 补列（幂等）
    op.execute("ALTER TABLE soc_role_menus ADD COLUMN IF NOT EXISTS permissions JSONB")
    op.execute("ALTER TABLE soc_roles ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true")
    op.execute("ALTER TABLE soc_users ADD COLUMN IF NOT EXISTS nick_name VARCHAR(50)")
    op.execute("ALTER TABLE soc_users ADD COLUMN IF NOT EXISTS phone VARCHAR(20)")
    op.execute("ALTER TABLE soc_users ADD COLUMN IF NOT EXISTS avatar VARCHAR(255)")
    op.execute("ALTER TABLE soc_users ADD COLUMN IF NOT EXISTS gender INTEGER")
    op.execute("ALTER TABLE soc_users ADD COLUMN IF NOT EXISTS department_id BIGINT")


def downgrade() -> None:
    # 欠账表/列在旧库中本就可能不存在（手工建的），downgrade 仅做 best-effort
    for tname in reversed(_TABLES_TO_CREATE):
        op.execute(f'DROP TABLE IF EXISTS "{tname}" CASCADE')
    op.execute("ALTER TABLE soc_users DROP COLUMN IF EXISTS department_id")
    op.execute("ALTER TABLE soc_users DROP COLUMN IF EXISTS gender")
    op.execute("ALTER TABLE soc_users DROP COLUMN IF EXISTS avatar")
    op.execute("ALTER TABLE soc_users DROP COLUMN IF EXISTS phone")
    op.execute("ALTER TABLE soc_users DROP COLUMN IF EXISTS nick_name")
    op.execute("ALTER TABLE soc_roles DROP COLUMN IF EXISTS is_active")
    op.execute("ALTER TABLE soc_role_menus DROP COLUMN IF EXISTS permissions")
