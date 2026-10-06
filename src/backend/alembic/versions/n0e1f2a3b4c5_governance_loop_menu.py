"""OH-7.4 治理闭环看板菜单种子

菜单「治理闭环」挂「资产管理」(id=2) 下，sort_order=13：
  path='governance-loop', component='/asset/governance-loop/index'
只读看板，四角色可读。

Revision ID: n0e1f2a3b4c5
Revises: m9d0e1f2a3b4
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "n0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "m9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None

_MENU_PERMS = '[{"title": "查看", "authMark": "view"}]'


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(sa.text(
        "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
        "  is_visible, component, permissions) "
        "SELECT 2, '治理闭环', '治理闭环', 'governance-loop', "
        "  'ri:loop-left-line', 13, TRUE, '/asset/governance-loop/index', "
        "  CAST(:perms AS jsonb) "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM soc_menus WHERE parent_id = 2 AND path = 'governance-loop')"),
        {"perms": _MENU_PERMS},
    )

    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[\"view\"]' AS jsonb) "
        "FROM soc_roles r JOIN soc_menus m ON m.parent_id = 2 "
        "  AND m.path = 'governance-loop' "
        "WHERE r.code IN ('admin', 'operator', 'viewer', 'auditor') "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM soc_role_menus rm USING soc_menus m "
        "WHERE rm.menu_id = m.id AND m.parent_id = 2 "
        "  AND m.path = 'governance-loop'"))
    bind.execute(sa.text(
        "DELETE FROM soc_menus WHERE parent_id = 2 AND path = 'governance-loop'"))
