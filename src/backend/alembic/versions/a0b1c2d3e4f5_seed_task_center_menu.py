"""seed task-center menu (v0.4.2 Phase 1.7)

Revision ID: a0b1c2d3e4f5
Revises: f9a0b1c2d3e4
Create Date: 2026-08-17 00:30:00.000000

插入"任务中心"菜单到系统管理（parent_id=5）下，授权给 admin 角色。
幂等：重复执行不会重复插入。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "f9a0b1c2d3e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MENU_PERMISSIONS = sa.text("""'[
    {"title": "查看", "authMark": "view"},
    {"title": "手动触发", "authMark": "trigger"},
    {"title": "取消", "authMark": "cancel"},
    {"title": "启用/禁用", "authMark": "toggle"},
    {"title": "查看历史", "authMark": "view_runs"}
]'::jsonb""")


def upgrade() -> None:
    # 幂等插入菜单（DO NOTHING 若 path+parent_id 已存在）
    op.execute(
        sa.text(
            """
            INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                                   sort_order, is_visible, permissions, created_at, updated_at)
            SELECT 5, 'TaskCenter', '任务中心', 'task-center', 'ri:list-check-2',
                   '/system/task-center/index', 90, TRUE,
                   """
            + str(MENU_PERMISSIONS)
            + """,
                   now(), now()
            WHERE NOT EXISTS (
                SELECT 1 FROM soc_menus
                WHERE parent_id = 5 AND path = 'task-center'
            )
            """
        )
    )
    # 授权给 admin 角色（幂等），并授予全部按钮权限
    op.execute(
        sa.text(
            """
            INSERT INTO soc_role_menus (role_id, menu_id, permissions)
            SELECT r.id, m.id,
                   '["view","trigger","cancel","toggle","view_runs"]'::jsonb
            FROM soc_roles r
            JOIN soc_menus m ON m.parent_id = 5 AND m.path = 'task-center'
            WHERE r.code = 'admin'
              AND NOT EXISTS (
                  SELECT 1 FROM soc_role_menus rm
                  WHERE rm.role_id = r.id AND rm.menu_id = m.id
              )
            """
        )
    )
    # 若已存在关联但 permissions 为空（旧数据），补齐全部按钮权限
    op.execute(
        sa.text(
            """
            UPDATE soc_role_menus rm
            SET permissions = '["view","trigger","cancel","toggle","view_runs"]'::jsonb
            FROM soc_roles r, soc_menus m
            WHERE rm.role_id = r.id AND rm.menu_id = m.id
              AND r.code = 'admin' AND m.path = 'task-center'
              AND (rm.permissions IS NULL OR rm.permissions::text = '[]')
            """
        )
    )
    # 图标修正为 iconify 格式（旧版误写为 'Warning'）
    op.execute(sa.text("UPDATE soc_menus SET icon='ri:list-check-2' WHERE path='task-center' AND icon='Warning'"))


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM soc_role_menus
            WHERE menu_id IN (
                SELECT id FROM soc_menus WHERE parent_id = 5 AND path = 'task-center'
            )
            """
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM soc_menus WHERE parent_id = 5 AND path = 'task-center'"
        )
    )
