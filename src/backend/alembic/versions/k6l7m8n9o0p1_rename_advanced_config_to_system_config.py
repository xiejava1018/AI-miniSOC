"""菜单改名：高级配置(KV) → 系统配置

Revision ID: k6l7m8n9o0p1
Revises: j5k6l7m8n9o0
Create Date: 2026-09-13

用户 2026-09-13 指定：
系统管理下的「高级配置(KV)」菜单改名为「系统配置」。

只改显示字段（name + title），path='system-config' 不变（前端路由继续可用），
icon 不变（ri:settings-2-line）。

前端引用检查：src/frontend/src/ 内 system-config 字符串仅出现在 .vue class 名和 API path
（/api/v1/system-configs），与菜单显示无关——无需前端改动。
"""
from alembic import op
import sqlalchemy as sa

revision = "k6l7m8n9o0p1"
down_revision = "j5k6l7m8n9o0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET name = '系统配置',
                title = '系统配置',
                updated_at = NOW()
            WHERE path = 'system-config'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET name = '高级配置KV',
                title = '高级配置(KV)',
                updated_at = NOW()
            WHERE path = 'system-config'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
            """
        )
    )
