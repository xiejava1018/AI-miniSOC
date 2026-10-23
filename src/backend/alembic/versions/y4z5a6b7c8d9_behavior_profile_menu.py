"""behavior profile menu (Phase 2, 方案 §9.5 v1.5)

「行为画像」子菜单挂「上网行为」（path=/browsing）下（sort_order=7）。
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

    # 2026-10（issue #12）：原写 `parent_id = 22`（硬编码生产库「行为分析」的 id）。
    # 空库上 22 号是别的菜单（「行为分析」的 id 随插入顺序而定），
    # 于是「行为画像」被挂到错误父菜单下 → 前端路由错位 / 500。
    # 改为按 path 反查父菜单（CLAUDE.md §4.3 红线②：不硬编码 id）。
    _PARENT = "p.path = '/browsing' AND p.parent_id IS NULL"

    # 1) 菜单（幂等：parent+path 唯一判定）
    bind.execute(sa.text(
        "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
        "  is_visible, component, permissions) "
        "SELECT p.id, '行为画像', '行为画像', 'profile', 'ri:user-search-line', 7, "
        "  TRUE, '/browsing/profile/index', CAST(:perms AS jsonb) "
        "FROM soc_menus p WHERE " + _PARENT +
        "  AND NOT EXISTS ("
        "    SELECT 1 FROM soc_menus m WHERE m.parent_id = p.id AND m.path = 'profile')"),
        {"perms": _MENU_PERMS},
    )

    # 2) 角色授权（JOIN 角色表按 code，不硬编码 id；幂等 NOT EXISTS）
    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST(:admin_perms AS jsonb) "
        "FROM soc_roles r "
        "JOIN soc_menus p ON " + _PARENT +
        " JOIN soc_menus m ON m.parent_id = p.id AND m.path = 'profile' "
        "WHERE r.code = 'admin' "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"),
        {"admin_perms": '["refresh"]'},
    )
    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[]' AS jsonb) "
        "FROM soc_roles r "
        "JOIN soc_menus p ON " + _PARENT +
        " JOIN soc_menus m ON m.parent_id = p.id AND m.path = 'profile' "
        "WHERE r.code = 'auditor' "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"))


def downgrade() -> None:
    bind = op.get_bind()
    # 先删授权再删菜单（FK CASCADE 也能兜底，但显式更清晰）
    bind.execute(sa.text(
        "DELETE FROM soc_role_menus rm USING soc_menus p, soc_menus m "
        "WHERE rm.menu_id = m.id AND m.parent_id = p.id AND m.path = 'profile' "
        "AND p.path = '/browsing' AND p.parent_id IS NULL"))
    bind.execute(sa.text(
        "DELETE FROM soc_menus m USING soc_menus p "
        "WHERE m.parent_id = p.id AND m.path = 'profile' "
        "AND p.path = '/browsing' AND p.parent_id IS NULL"))
