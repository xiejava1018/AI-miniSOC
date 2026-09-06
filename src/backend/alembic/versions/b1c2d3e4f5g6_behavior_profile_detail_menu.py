"""behavior profile L2 hidden route menu (两层结构改造 S4, 2026-09-06)

插入隐藏菜单行（is_visible=false，不占侧边栏）：
  parent=/browsing(id 按路径反查，勿硬编码)
  path='profile/detail/:ip', component='/browsing/profile/detail'
授权：所有已拥有「行为画像」子菜单(path='profile')的角色自动获得该隐藏路由
（INSERT ... SELECT ... WHERE NOT EXISTS，幂等；纯 SQL，--sql dry-run 可跑）。

Revision ID: b1c2d3e4f5g6
Revises: z6a7b8c9d0e1
Create Date: 2026-09-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b1c2d3e4f5g6"
down_revision: Union[str, Sequence[str], None] = "z6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MENU_PATH = "profile/detail/:ip"


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 隐藏菜单行（parent 按路径反查，幂等）
    bind.execute(sa.text(
        """
        INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order,
                               is_visible, component, permissions, created_at, updated_at)
        SELECT p.id, '画像详情', '画像详情', :menu_path, 'ri:user-search-line', 9,
               FALSE, '/browsing/profile/detail', CAST('[]' AS jsonb), NOW(), NOW()
        FROM soc_menus p
        WHERE p.path = '/browsing' AND p.parent_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM soc_menus m
              WHERE m.path = :menu_path AND m.parent_id = p.id
          )
        """
    ), {"menu_path": _MENU_PATH})

    # 2) 授权：已有「行为画像」菜单的角色 → 同步授隐藏路由
    bind.execute(sa.text(
        """
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT rm.role_id, m.id, CAST('[]' AS jsonb)
        FROM soc_role_menus rm
        JOIN soc_menus pm ON pm.id = rm.menu_id AND pm.path = 'profile'
        JOIN soc_menus p ON p.path = '/browsing' AND p.parent_id IS NULL
        JOIN soc_menus m ON m.path = :menu_path AND m.parent_id = p.id
        WHERE NOT EXISTS (
            SELECT 1 FROM soc_role_menus x
            WHERE x.role_id = rm.role_id AND x.menu_id = m.id
        )
        """
    ), {"menu_path": _MENU_PATH})


def downgrade() -> None:
    bind = op.get_bind()
    # 先删授权再删菜单行（FK 安全顺序）
    bind.execute(sa.text(
        """
        DELETE FROM soc_role_menus
        WHERE menu_id IN (SELECT id FROM soc_menus WHERE path = :menu_path)
        """
    ), {"menu_path": _MENU_PATH})
    bind.execute(sa.text(
        "DELETE FROM soc_menus WHERE path = :menu_path"
    ), {"menu_path": _MENU_PATH})
