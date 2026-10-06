"""OH-UI.8 本体对齐视图菜单种子

菜单「本体对齐」挂「资产管理」(id=2) 下，sort_order=15：
  path='ontology-view', component='/asset/ontology-view/index'
只读视图，四角色可读。

Revision ID: p2a3b4c5d6e7
Revises: o1f2a3b4c5d6
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "p2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "o1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None

_MENU_PERMS = '[{"title": "查看", "authMark": "view"}]'


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(sa.text(
        "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
        "  is_visible, component, permissions) "
        "SELECT 2, '本体对齐', '本体对齐', 'ontology-view', "
        "  'ri:share-circle-2-line', 15, TRUE, '/asset/ontology-view/index', "
        "  CAST(:perms AS jsonb) "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM soc_menus WHERE parent_id = 2 "
        "    AND path = 'ontology-view')"),
        {"perms": _MENU_PERMS},
    )

    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[\"view\"]' AS jsonb) "
        "FROM soc_roles r JOIN soc_menus m ON m.parent_id = 2 "
        "  AND m.path = 'ontology-view' "
        "WHERE r.code IN ('admin', 'operator', 'viewer', 'auditor') "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM soc_role_menus rm USING soc_menus m "
        "WHERE rm.menu_id = m.id AND m.parent_id = 2 "
        "  AND m.path = 'ontology-view'"))
    bind.execute(sa.text(
        "DELETE FROM soc_menus WHERE parent_id = 2 AND path = 'ontology-view'"))
