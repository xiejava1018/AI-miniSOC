"""
P3 资产扫描控制面：种菜单 + 4 角色 × 4 菜单授权（X1 权限矩阵扩展）

设计依据：docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md §6.4.1

菜单结构：
  顶级 /scan (sort_order=10，介于 /system 9 之后)
    - scanners        /scan/scanners
    - tasks           /scan/tasks
    - findings        /scan/findings

权限矩阵（X1 扩展）：
  - scan_view          viewer+ 都能看（只读）
  - scan_run           operator / admin（建任务/取消）
  - scan_finding_manage operator / admin（一键纳管/忽略）
  - scan_target_manage operator / admin（管理扫描目标）—— Phase 2 简化为 scan_view 即可

CLAUDE.md 教训（:1189）：迁移里用 IF NOT EXISTS 写法 + 父菜单按 path 子查询（不要硬编码 id），
         重复跑幂等；本迁移可被 CI 多次执行。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "o1p2q3r4s5t6"
down_revision: Union[str, Sequence[str], None] = "n1o2p3q4r5s6"
branch_labels = None
depends_on = None


# 菜单按钮权限定义（JSONB 数组）
SCAN_MENU_PERMISSIONS = [
    {"title": "触发扫描", "authMark": "scan_run"},
    {"title": "一键纳管/忽略", "authMark": "scan_finding_manage"},
    {"title": "查看历史/发现", "authMark": "scan_view"},
]


def _role_id(code: str) -> int:
    """子查询拿 role id（避免硬编码）。"""
    return op.get_bind().execute(
        sa.text("SELECT id FROM soc_roles WHERE code = :code"), {"code": code}
    ).scalar()


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 种顶级 /scan 菜单（path 是 kebab-case 顶级约定）
    bind.execute(
        sa.text(
            """
            INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                                   sort_order, is_visible, permissions, created_at, updated_at)
            SELECT NULL, 'scan', '资产扫描', '/scan', 'ri:radar-line', '/scan/index',
                   10, TRUE,
                   '[{"title":"触发扫描","authMark":"scan_run"},{"title":"一键纳管/忽略","authMark":"scan_finding_manage"},{"title":"查看历史/发现","authMark":"scan_view"}]'::jsonb,
                   NOW(), NOW()
            WHERE NOT EXISTS (
                SELECT 1 FROM soc_menus WHERE path = '/scan' AND parent_id IS NULL
            )
            """
        )
    )

    # 2. 种 3 个子菜单（ID 走子查询）
    sub_menus = [
        {"name": "scanners", "title": "扫描器", "path": "scanners",
         "component": "/scan/scanners/index", "sort_order": 1},
        {"name": "tasks",    "title": "扫描任务", "path": "tasks",
         "component": "/scan/tasks/index", "sort_order": 2},
        {"name": "findings", "title": "发现清单", "path": "findings",
         "component": "/scan/findings/index", "sort_order": 3},
    ]
    for m in sub_menus:
        bind.execute(
            sa.text(
                """
                INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                                       sort_order, is_visible, permissions, created_at, updated_at)
                SELECT (SELECT id FROM soc_menus WHERE path = '/scan' AND parent_id IS NULL),
                       :name, :title, :path, 'ri:radar-line', :component,
                       :sort_order, TRUE, '[]'::jsonb, NOW(), NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM soc_menus m
                    WHERE m.path = :path
                      AND m.parent_id = (SELECT id FROM soc_menus WHERE path = '/scan' AND parent_id IS NULL)
                )
                """
            ),
            {
                "name": m["name"], "title": m["title"], "path": m["path"],
                "component": m["component"], "sort_order": m["sort_order"],
            },
        )

    # 3. 角色授权（X1 矩阵）—— 使用静态 SQL，避免动态参数拼装（CLAUDE.md 教训）
    # admin: 全部；operator: scan_run + scan_finding_manage + scan_view
    # viewer / auditor: scan_view
    # 结构：每个 (role, menu) 一条 INSERT，权限数组走 jsonb_build_array
    auth_grants = [
        # (role_code, menu_name, jsonb_array_of_auth_marks)
        ("admin", "scan",
         '["scan_run","scan_finding_manage","scan_view"]'),
        ("admin", "scanners", '["scan_view"]'),
        ("admin", "tasks",
         '["scan_run","scan_view"]'),
        ("admin", "findings",
         '["scan_run","scan_finding_manage","scan_view"]'),

        ("operator", "scan",
         '["scan_run","scan_finding_manage","scan_view"]'),
        ("operator", "scanners", '["scan_view"]'),
        ("operator", "tasks",
         '["scan_run","scan_view"]'),
        ("operator", "findings",
         '["scan_run","scan_finding_manage","scan_view"]'),

        ("viewer", "scan", '["scan_view"]'),
        ("viewer", "scanners", '["scan_view"]'),
        ("viewer", "tasks", '["scan_view"]'),
        ("viewer", "findings", '["scan_view"]'),

        ("auditor", "scan", '["scan_view"]'),
        ("auditor", "scanners", '["scan_view"]'),
        ("auditor", "tasks", '["scan_view"]'),
        ("auditor", "findings", '["scan_view"]'),
    ]
    for code, menu_name, perms_json in auth_grants:
        bind.execute(
            sa.text(
                """
                INSERT INTO soc_role_menus (role_id, menu_id, permissions)
                SELECT r.id, m.id, CAST(:perms AS jsonb)
                FROM soc_roles r, soc_menus m
                WHERE r.code = :code AND m.name = :menu_name
                  AND NOT EXISTS (
                      SELECT 1 FROM soc_role_menus rm
                      WHERE rm.role_id = r.id AND rm.menu_id = m.id
                  )
                """
            ),
            {"code": code, "menu_name": menu_name, "perms": perms_json},
        )


def downgrade() -> None:
    """降级：删 /scan 菜单（级联删 soc_role_menus）。"""
    op.execute(
        sa.text(
            """
            DELETE FROM soc_menus
            WHERE path = '/scan' AND parent_id IS NULL
               OR parent_id = (SELECT id FROM soc_menus WHERE path = '/scan' AND parent_id IS NULL)
            """
        )
    )