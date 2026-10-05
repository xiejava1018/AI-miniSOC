"""OH-UI.11 定级稽核视图菜单种子

菜单「定级稽核」挂「资产管理」(id=2) 下，sort_order=12：
  path='rating-audit', component='/asset/rating-audit/index'
只读视图（view），四角色可读（稽核数据对 viewer/auditor 开放）。

Revision ID: l8c9d0e1f2a3
Revises: k7b8c9d0e1f2
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "l8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "k7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None

_MENU_PERMS = '[{"title": "查看", "authMark": "view"}]'


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(sa.text(
        "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
        "  is_visible, component, permissions) "
        "SELECT 2, '定级稽核', '定级稽核', 'rating-audit', 'ri:file-shield-2-line', "
        "  12, TRUE, '/asset/rating-audit/index', CAST(:perms AS jsonb) "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM soc_menus WHERE parent_id = 2 AND path = 'rating-audit')"),
        {"perms": _MENU_PERMS},
    )

    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[\"view\"]' AS jsonb) "
        "FROM soc_roles r JOIN soc_menus m ON m.parent_id = 2 AND m.path = 'rating-audit' "
        "WHERE r.code IN ('admin', 'operator', 'viewer', 'auditor') "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM soc_role_menus rm USING soc_menus m "
        "WHERE rm.menu_id = m.id AND m.parent_id = 2 AND m.path = 'rating-audit'"))
    bind.execute(sa.text(
        "DELETE FROM soc_menus WHERE parent_id = 2 AND path = 'rating-audit'"))
