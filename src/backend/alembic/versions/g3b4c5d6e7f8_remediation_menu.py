"""OH-UI.13 整改工单菜单种子

菜单「整改工单」挂「资产管理」(id=2) 下，sort_order=11：
  path='remediation', component='/asset/remediation/index'
  permissions: view / assign / advance
授权对齐 API（require_button_permission("remediation", ...)）：
  admin/operator 全量；viewer/auditor 只读
种子纯 SQL INSERT…SELECT + NOT EXISTS 幂等，JOIN 菜单/角色表，不硬编码 id；
soc_role_menus 只有 role_id/menu_id/permissions 三列。

Revision ID: g3b4c5d6e7f8
Revises: f1a2b3c4d5e6
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "g3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None

_MENU_PERMS = (
    '[{"title": "查看", "authMark": "view"},'
    ' {"title": "指派", "authMark": "assign"},'
    ' {"title": "流转", "authMark": "advance"}]'
)


def upgrade() -> None:
    bind = op.get_bind()

    bind.execute(sa.text(
        "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
        "  is_visible, component, permissions) "
        "SELECT 2, '整改工单', '整改工单', 'remediation', 'ri:tools-line', 11, "
        "  TRUE, '/asset/remediation/index', CAST(:perms AS jsonb) "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM soc_menus WHERE parent_id = 2 AND path = 'remediation')"),
        {"perms": _MENU_PERMS},
    )

    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[\"view\", \"assign\", \"advance\"]' AS jsonb) "
        "FROM soc_roles r JOIN soc_menus m ON m.parent_id = 2 AND m.path = 'remediation' "
        "WHERE r.code IN ('admin', 'operator') "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"))
    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[\"view\"]' AS jsonb) "
        "FROM soc_roles r JOIN soc_menus m ON m.parent_id = 2 AND m.path = 'remediation' "
        "WHERE r.code IN ('viewer', 'auditor') "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM soc_role_menus rm USING soc_menus m "
        "WHERE rm.menu_id = m.id AND m.parent_id = 2 AND m.path = 'remediation'"))
    bind.execute(sa.text(
        "DELETE FROM soc_menus WHERE parent_id = 2 AND path = 'remediation'"))
