"""graph perf-dashboard menu (OH-3.6, 跟踪表 §五 T-7)

「图谱性能看板」子菜单挂「资产管理」id=2 下（sort_order=9）。
- path: 'graph/perf-dashboard'（前端 routesAlias AssetGraphPerf = '/asset/graph/perf-dashboard/index'）
- component: '/asset/graph/perf-dashboard/index'（前端 Vue 文件路径）
- permissions: 查看（authMark=view）；admin / operator / auditor（与 require_role 对齐）
- 幂等：parent_id + path 唯一判定 → NOT EXISTS

依据：跟踪表 §五 T-7 菜单注册缺位会让后端 /api/v1/graph/perf 端点挂不到 UI。
本迁移填补 /assets 子菜单的空白位（sort_order=9，原 1-8 已满）。

注意：
  - 不修改 parent 菜单 =「资产管理」(id=2)
  - 不修改同级兄弟菜单（graph 已是 id=72 / sort_order=7）
  - icon='ri:dashboard-2-line'（已在 icones.js.org 校验存在）

Revision ID: b6c7d8e9f0a1
Revises: 4d5e6f7a8b9c
Create Date: 2026-10-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b6c7d8e9f0a1"
down_revision: Union[str, Sequence[str], None] = "4d5e6f7a8b9c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_MENU_PERMS = '[{"title": "查看", "authMark": "view"}, {"title": "重置采样", "authMark": "reset"}]'

# 与 api/graph.py require_role("viewer","operator","admin","auditor") 对齐
# viewer 也只读 — 但仅 admin 能 reset；写入走 role_menus 的 permissions JSON 字段
_ROLE_PERMS_VIEWER = '["view"]'
_ROLE_PERMS_OPERATOR = '["view"]'
_ROLE_PERMS_ADMIN = '["view", "reset"]'
_ROLE_PERMS_AUDITOR = '["view"]'


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 菜单（幂等：parent_id + path 唯一判定）
    bind.execute(sa.text(
        "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
        "  is_visible, component, permissions) "
        "SELECT 2, '图谱性能看板', '图谱性能看板', 'graph/perf-dashboard', "
        "       'ri:dashboard-2-line', 9, "
        "       TRUE, '/asset/graph/perf-dashboard/index', CAST(:perms AS jsonb) "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM soc_menus WHERE parent_id = 2 AND path = 'graph/perf-dashboard')"),
        {"perms": _MENU_PERMS},
    )

    # 2) 角色授权（JOIN 角色表按 code，不硬编码 id；幂等 NOT EXISTS）
    for role_code, perms in (
        ("admin", _ROLE_PERMS_ADMIN),
        ("operator", _ROLE_PERMS_OPERATOR),
        ("viewer", _ROLE_PERMS_VIEWER),
        ("auditor", _ROLE_PERMS_AUDITOR),
    ):
        bind.execute(sa.text(
            "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
            "SELECT r.id, m.id, CAST(:perms AS jsonb) "
            "FROM soc_roles r JOIN soc_menus m ON m.parent_id = 2 AND m.path = 'graph/perf-dashboard' "
            "WHERE r.code = :code "
            "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
            "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"),
            {"code": role_code, "perms": perms},
        )


def downgrade() -> None:
    bind = op.get_bind()
    # 删除授权 + 菜单（自下而上，避免孤儿）
    bind.execute(sa.text(
        "DELETE FROM soc_role_menus "
        "WHERE menu_id IN (SELECT id FROM soc_menus "
        "                  WHERE parent_id = 2 AND path = 'graph/perf-dashboard')"
    ))
    bind.execute(sa.text(
        "DELETE FROM soc_menus WHERE parent_id = 2 AND path = 'graph/perf-dashboard'"
    ))
