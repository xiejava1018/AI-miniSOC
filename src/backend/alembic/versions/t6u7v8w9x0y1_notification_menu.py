"""OH-NOT-F2 通知菜单种子：「通知通道」(admin) + 「通知偏好」(全角色)

挂「系统管理」(/system) 下：
  - notification-channels  通知通道   admin only（SMTP 配置）
  - notification-preferences 通知偏好 全角色（per type × channel 开关）

CLAUDE.md §4.4 约定：icon 用 ri:*（icones.js.org 真实存在）；父菜单按 title
定位（name 历史上中英混用，title 稳定）；NOT EXISTS 幂等。

Revision ID: t6u7v8w9x0y1
Revises: s5t6u7v8w9x0
Create Date: 2026-10-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "t6u7v8w9x0y1"
down_revision: Union[str, Sequence[str], None] = "s5t6u7v8w9x0"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None

_MENU_PERMS_VIEW = '[{"title": "查看", "authMark": "view"}]'


def upgrade() -> None:
    bind = op.get_bind()

    # ---- 1. 菜单行（父 = 系统管理，按 title 定位不硬编码 id）----
    bind.execute(sa.text(
        "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
        "  is_visible, component, permissions) "
        "SELECT p.id, 'notificationChannels', '通知通道', 'notification-channels', "
        "  'ri:mail-line', 8, TRUE, '/system/notification-channels', CAST(:perms AS jsonb) "
        "FROM (SELECT id FROM soc_menus WHERE title = '系统管理' AND parent_id IS NULL) p "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM soc_menus m WHERE m.parent_id = p.id "
        "    AND m.path = 'notification-channels')"),
        {"perms": _MENU_PERMS_VIEW},
    )

    bind.execute(sa.text(
        "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
        "  is_visible, component, permissions) "
        "SELECT p.id, 'notificationPrefs', '通知偏好', 'notification-preferences', "
        "  'ri:notification-3-line', 9, TRUE, '/system/notification-preferences', "
        "  CAST(:perms AS jsonb) "
        "FROM (SELECT id FROM soc_menus WHERE title = '系统管理' AND parent_id IS NULL) p "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM soc_menus m WHERE m.parent_id = p.id "
        "    AND m.path = 'notification-preferences')"),
        {"perms": _MENU_PERMS_VIEW},
    )

    # ---- 2. 授权：通知通道 → admin；通知偏好 → 全角色 ----
    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[\"view\"]' AS jsonb) "
        "FROM soc_roles r "
        "JOIN soc_menus p ON p.title = '系统管理' AND p.parent_id IS NULL "
        "JOIN soc_menus m ON m.parent_id = p.id AND m.path = 'notification-channels' "
        "WHERE r.code = 'admin' "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"))

    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[\"view\"]' AS jsonb) "
        "FROM soc_roles r "
        "JOIN soc_menus p ON p.title = '系统管理' AND p.parent_id IS NULL "
        "JOIN soc_menus m ON m.parent_id = p.id AND m.path = 'notification-preferences' "
        "WHERE r.code IN ('admin', 'operator', 'viewer', 'auditor') "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM soc_role_menus rm USING soc_menus m "
        "WHERE rm.menu_id = m.id "
        "  AND m.path IN ('notification-channels', 'notification-preferences') "
        "  AND m.parent_id IN (SELECT id FROM soc_menus "
        "                      WHERE title = '系统管理' AND parent_id IS NULL)"))
    bind.execute(sa.text(
        "DELETE FROM soc_menus WHERE path IN ('notification-channels', "
        "  'notification-preferences') "
        "  AND parent_id IN (SELECT id FROM soc_menus "
        "                     WHERE title = '系统管理' AND parent_id IS NULL)"))
