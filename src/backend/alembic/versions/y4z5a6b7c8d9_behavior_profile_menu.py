"""behavior profile menu (Phase 2, 方案 §9.5 v1.5)

「行为画像」子菜单挂「上网行为」id=22 下（sort_order=7）。
- permissions 种在子菜单自己身上（authMark=refresh，o1p2q3r4s5t6 教训：种父容器 hasAuth 恒 false）
- 授权：admin 全量、auditor 只读（对齐 API 权限 require_role("admin","auditor")）
- 纯 SQL INSERT…SELECT + NOT EXISTS 幂等；soc_role_menus 无 created_at 列

Revision ID: y4z5a6b7c8d9
Revises: x3y4z5a6b7c8
Create Date: 2026-09-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "y4z5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "x3y4z5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MENU_PERMS = '[{"title": "实时刷新", "authMark": "refresh"}]'


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 菜单（幂等：parent+path 唯一判定）
    bind.execute(sa.text(
        "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
        "  is_visible, component, permissions) "
        "SELECT 22, '行为画像', '行为画像', 'profile', 'ri:user-search-line', 7, "
        "  TRUE, '/browsing/profile/index', CAST(:perms AS jsonb) "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM soc_menus WHERE parent_id = 22 AND path = 'profile')"),
        {"perms": _MENU_PERMS},
    )

    # 2) 角色授权（JOIN 角色表按 code，不硬编码 id；幂等 NOT EXISTS）
    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST(:admin_perms AS jsonb) "
        "FROM soc_roles r JOIN soc_menus m ON m.parent_id = 22 AND m.path = 'profile' "
        "WHERE r.code = 'admin' "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"),
        {"admin_perms": '["refresh"]'},
    )
    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[]' AS jsonb) "
        "FROM soc_roles r JOIN soc_menus m ON m.parent_id = 22 AND m.path = 'profile' "
        "WHERE r.code = 'auditor' "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"))


def downgrade() -> None:
    bind = op.get_bind()
    # 先删授权再删菜单（FK CASCADE 也能兜底，但显式更清晰）
    bind.execute(sa.text(
        "DELETE FROM soc_role_menus rm USING soc_menus m "
        "WHERE rm.menu_id = m.id AND m.parent_id = 22 AND m.path = 'profile'"))
    bind.execute(sa.text(
        "DELETE FROM soc_menus WHERE parent_id = 22 AND path = 'profile'"))
