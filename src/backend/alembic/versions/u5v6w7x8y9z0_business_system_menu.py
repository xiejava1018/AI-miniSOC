"""业务系统管理菜单（v1 §7.0 WO-0a / §7.2.5 F9）

补齐 §6 工程闭环之外的组织数据入口：
- 「系统管理」下挂子菜单「业务系统管理」，path=business-system, component=/system/business-system/index
- 父容器「系统管理」沿用 /system（已有 /index/index 容器组件）
- 权限：admin 全部 + operator/viewer/auditor 仅读（与 API 写端 require_admin 对齐）
- 纯 SQL INSERT…SELECT + NOT EXISTS 幂等；
  - 不硬编码 parent_id：通过 JOIN 父菜单 path 定位
  - soc_role_menus 无 created_at/updated_at 列（CLAUDE.md 既有教训）

Revision ID: u5v6w7x8y9z0
Revises: t3u4v5w6x7y8
Create Date: 2026-09-14
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u5v6w7x8y9z0"
down_revision: Union[str, Sequence[str], None] = "t3u4v5w6x7y8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MENU_PERMS = '[{"title": "新增", "authMark": "add"}, {"title": "编辑", "authMark": "edit"}, {"title": "删除", "authMark": "delete"}]'


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 菜单（幂等：parent_id + path 唯一判定）
    bind.execute(sa.text("""
        INSERT INTO soc_menus
            (parent_id, name, title, path, icon, component, sort_order, is_visible, permissions, created_at, updated_at)
        SELECT
            p.id,
            'business-system',
            '业务系统管理',
            'business-system',
            'ri:briefcase-line',
            '/system/business-system/index',
            8,
            TRUE,
            CAST(:perms AS jsonb),
            NOW(),
            NOW()
        FROM soc_menus p
        WHERE p.path = '/system' AND p.parent_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM soc_menus m
              WHERE m.path = 'business-system' AND m.parent_id = p.id
          )
    """), {"perms": _MENU_PERMS})

    # 2) 授权：admin 全量 + operator/viewer/auditor 仅读（无 perms，对应 API GET 可读）
    # 对齐 §7.2.5 F9「管理功能缺失」+ 与既有部门/字典管理授权风格
    # admin 写权限：种全 perms（add/edit/delete）→ API require_admin 再兜底
    # 其他角色：仅只读 → 种空 perms []，UI 不显示按钮
    bind.execute(sa.text("""
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, m.id, CAST(:admin_perms AS jsonb)
        FROM soc_roles r, soc_menus m
        WHERE r.code = 'admin'
          AND m.path = 'business-system' AND m.parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
          AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm WHERE rm.role_id = r.id AND rm.menu_id = m.id)
    """), {"admin_perms": _MENU_PERMS})

    bind.execute(sa.text("""
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, m.id, CAST('[]' AS jsonb)
        FROM soc_roles r, soc_menus m
        WHERE r.code IN ('operator', 'viewer', 'auditor')
          AND m.path = 'business-system' AND m.parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
          AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm WHERE rm.role_id = r.id AND rm.menu_id = m.id)
    """))


def downgrade() -> None:
    bind = op.get_bind()
    # 仅删本迁移建的菜单（按 path 定位）+ 角色授权
    bind.execute(sa.text("""
        DELETE FROM soc_role_menus
        WHERE menu_id IN (
            SELECT id FROM soc_menus
            WHERE path = 'business-system'
              AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
        )
    """))
    bind.execute(sa.text("""
        DELETE FROM soc_menus
        WHERE path = 'business-system'
          AND parent_id = (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL)
    """))
