"""OH-UI.6 数字员工统一对话工作空间菜单种子

菜单「资产数字员工」挂「资产管理」(id=2) 下，sort_order=14：
  path='agent-workbench', component='/asset/agent-workbench/index'
问答工作空间，四角色可用（登录用户均可向数字员工提问）。

Revision ID: o1f2a3b4c5d6
Revises: n0e1f2a3b4c5
Create Date: 2026-10-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "o1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "n0e1f2a3b4c5"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None

_MENU_PERMS = '[{"title": "查看", "authMark": "view"}]'


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(sa.text(
        "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
        "  is_visible, component, permissions) "
        "SELECT 2, '资产数字员工', '资产数字员工', 'agent-workbench', "
        "  'ri:robot-2-line', 14, TRUE, '/asset/agent-workbench/index', "
        "  CAST(:perms AS jsonb) "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM soc_menus WHERE parent_id = 2 "
        "    AND path = 'agent-workbench')"),
        {"perms": _MENU_PERMS},
    )

    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[\"view\"]' AS jsonb) "
        "FROM soc_roles r JOIN soc_menus m ON m.parent_id = 2 "
        "  AND m.path = 'agent-workbench' "
        "WHERE r.code IN ('admin', 'operator', 'viewer', 'auditor') "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM soc_role_menus rm USING soc_menus m "
        "WHERE rm.menu_id = m.id AND m.parent_id = 2 "
        "  AND m.path = 'agent-workbench'"))
    bind.execute(sa.text(
        "DELETE FROM soc_menus WHERE parent_id = 2 AND path = 'agent-workbench'"))
