"""AI Provider 独立化：soc_ai_providers 表 + 菜单

Revision ID: h3i4j5k6l7m8
Revises: g2h3i4j5k6l7
Create Date: 2026-09-13

AI 模型配置从数据源管理拆出为独立业务对象：
- 建 soc_ai_providers（加密 key / 场景路由 / 默认实例 / 测试三件套）
- 菜单「AI 模型管理」挂 /system 下（component /system/ai-provider）
- admin 授权（view/add/edit/delete/test）
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "h3i4j5k6l7m8"
down_revision = "g2h3i4j5k6l7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "soc_ai_providers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("provider_code", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("protocol", sa.String(32), nullable=False, server_default="openai"),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("scenes", JSONB(), nullable=False, server_default="[]"),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("remark", sa.String(500), nullable=True),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_ai_providers_enabled", "soc_ai_providers", ["enabled"]
    )

    # 菜单：挂 /system 下（子查询取 parent_id，不硬编码）
    bind.execute(
        sa.text(
            """
            INSERT INTO soc_menus (parent_id, name, title, path, icon, component, sort_order, is_visible, permissions)
            SELECT p.id, v.name, v.title, v.path, v.icon, v.component, v.sort_order, true, CAST(v.perms AS jsonb)
            FROM (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL) p
            CROSS JOIN (VALUES
              ('aiProvider', 'AI 模型管理', 'ai-provider', 'ri:robot-2-line', '/system/ai-provider', 13,
               '[{"title":"查看","authMark":"view"},{"title":"新增","authMark":"add"},{"title":"编辑","authMark":"edit"},{"title":"删除","authMark":"delete"},{"title":"连接测试","authMark":"test"}]')
            ) AS v(name, title, path, icon, component, sort_order, perms)
            WHERE NOT EXISTS (
              SELECT 1 FROM soc_menus m WHERE m.name = v.name AND m.parent_id = p.id
            )
            """
        )
    )

    # admin 授权（soc_role_menus 只有三列）
    bind.execute(
        sa.text(
            """
            INSERT INTO soc_role_menus (role_id, menu_id, permissions)
            SELECT r.id, m.id,
                   CAST((SELECT jsonb_agg(e->>'authMark') FROM jsonb_array_elements(m.permissions) e) AS jsonb)
            FROM soc_roles r
            CROSS JOIN soc_menus m
            WHERE r.code = 'admin' AND m.name = 'aiProvider'
              AND NOT EXISTS (
                SELECT 1 FROM soc_role_menus rm WHERE rm.role_id = r.id AND rm.menu_id = m.id
              )
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            "DELETE FROM soc_role_menus WHERE menu_id IN (SELECT id FROM soc_menus WHERE name = 'aiProvider')"
        )
    )
    bind.execute(sa.text("DELETE FROM soc_menus WHERE name = 'aiProvider'"))
    op.drop_index("ix_ai_providers_enabled", table_name="soc_ai_providers")
    op.drop_table("soc_ai_providers")
