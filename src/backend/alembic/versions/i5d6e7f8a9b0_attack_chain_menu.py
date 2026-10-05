"""OH-UI.10 ATT&CK 映射视图菜单种子

菜单「ATT&CK 映射」挂「告警管理」下（告警→技战术是告警侧视图）：
  path='attack-chain', component='/asset/attack-chain/index'
  permissions: view（只读视图，无写按钮）
admin/operator/viewer/auditor 全部可读。

Revision ID: i5d6e7f8a9b0
Revises: h4c5d6e7f8a9
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "i5d6e7f8a9b0"
down_revision: Union[str, Sequence[str], None] = "h4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None

_MENU_PERMS = '[{"title": "查看", "authMark": "view"}]'


def _parent_id(bind) -> int:
    """告警管理菜单 id（title 匹配，不硬编码）。"""
    row = bind.execute(sa.text(
        "SELECT id FROM soc_menus WHERE title = '告警管理' AND parent_id IS NULL"
    )).first()
    if row is None:
        # 兜底：按 path 匹配告警顶级菜单
        row = bind.execute(sa.text(
            "SELECT id FROM soc_menus WHERE path = 'alert' AND parent_id IS NULL"
        )).first()
    if row is None:
        raise RuntimeError("未找到告警管理顶级菜单，种子中止")
    return int(row[0])


def upgrade() -> None:
    bind = op.get_bind()
    parent = _parent_id(bind)

    bind.execute(sa.text(
        "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
        "  is_visible, component, permissions) "
        "SELECT :parent, 'ATT&CK 映射', 'ATT&CK 映射', 'attack-chain', "
        "  'ri:sword-line', 30, TRUE, '/asset/attack-chain/index', "
        "  CAST(:perms AS jsonb) "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM soc_menus WHERE parent_id = :parent "
        "    AND path = 'attack-chain')"),
        {"parent": parent, "perms": _MENU_PERMS},
    )

    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[\"view\"]' AS jsonb) "
        "FROM soc_roles r JOIN soc_menus m "
        "  ON m.parent_id = :parent AND m.path = 'attack-chain' "
        "WHERE r.code IN ('admin', 'operator', 'viewer', 'auditor') "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"),
        {"parent": parent},
    )


def downgrade() -> None:
    bind = op.get_bind()
    parent = _parent_id(bind)
    bind.execute(sa.text(
        "DELETE FROM soc_role_menus rm USING soc_menus m "
        "WHERE rm.menu_id = m.id AND m.parent_id = :parent "
        "  AND m.path = 'attack-chain'"), {"parent": parent})
    bind.execute(sa.text(
        "DELETE FROM soc_menus WHERE parent_id = :parent "
        "  AND path = 'attack-chain'"), {"parent": parent})
