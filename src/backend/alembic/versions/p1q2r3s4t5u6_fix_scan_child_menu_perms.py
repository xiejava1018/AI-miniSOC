"""fix scan child menu perms (move button perms from container to child rows)

Revision ID: p1q2r3s4t5u6
Revises: o1p2q3r4s5t6
Create Date: 2026-08-26

o1p2q3r4s5t6 把 scan_run/scan_finding_manage/scan_view 三个按钮权限全种在
父容器 /scan 上，但前端 hasAuth() 读的是「当前路由」（子菜单）自己的 authList。
子菜单 permissions 为 [] 导致页面内 v-if="hasAuth('scan_run')" 恒为 false。

本迁移：
  1. 给 3 个子菜单各自写 permissions（扫描器/任务/发现）
  2. 按角色给每个子菜单重新授权（admin/operator 写权限，viewer/auditor 只读）
  3. 父容器 /scan 的 permissions 保留（它本身无页面，仅作种子记录，不影响路由）

幂等：UPDATE ... WHERE + INSERT NOT EXISTS，可重复执行。
downgrade：把 3 个子菜单 permissions 清空回 []（不删 role_menus，避免影响审计）。
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'p1q2r3s4t5u6'
down_revision = 'o1p2q3r4s5t6'
branch_labels = None
depends_on = None


# name -> permissions JSON（子菜单自己的按钮权限）
CHILD_PERMS = {
    "scanners": [
        {"title": "查看", "authMark": "scan_view"},
        {"title": "注册/编辑/注销", "authMark": "scanner_manage"},
    ],
    "tasks": [
        {"title": "查看", "authMark": "scan_view"},
        {"title": "触发/取消扫描", "authMark": "scan_run"},
    ],
    "findings": [
        {"title": "查看", "authMark": "scan_view"},
        {"title": "一键纳管/忽略", "authMark": "scan_finding_manage"},
    ],
}

# role code -> { child menu name -> [authMark...] }
ROLE_GRANTS = {
    "admin": {
        "scanners": ["scan_view", "scanner_manage"],
        "tasks": ["scan_view", "scan_run"],
        "findings": ["scan_view", "scan_finding_manage"],
    },
    "operator": {
        # operator 能触发扫描、处理发现，但不管理扫描器本身（admin 职责）
        "scanners": ["scan_view"],
        "tasks": ["scan_view", "scan_run"],
        "findings": ["scan_view", "scan_finding_manage"],
    },
    "viewer": {
        "scanners": ["scan_view"],
        "tasks": ["scan_view"],
        "findings": ["scan_view"],
    },
    "auditor": {
        "scanners": ["scan_view"],
        "tasks": ["scan_view"],
        "findings": ["scan_view"],
    },
}


def upgrade() -> None:
    bind = op.get_bind()

    # 0. 父容器 /scan 的 component 改为 /index/index（Layout，与 /assets /ops /system 一致）；
    #    原值 /scan/index 会让 ComponentLoader 找 views/scan/index.vue（不存在）。
    bind.execute(
        sa.text(
            """
            UPDATE soc_menus
            SET component = '/index/index'
            WHERE path = '/scan' AND parent_id IS NULL
            """
        )
    )

    # 1. 更新 3 个子菜单的 permissions
    for name, perms in CHILD_PERMS.items():
        import json
        bind.execute(
            sa.text(
                """
                UPDATE soc_menus
                SET permissions = CAST(:perms AS jsonb)
                WHERE name = :name
                  AND parent_id = (SELECT id FROM soc_menus WHERE path = '/scan' AND parent_id IS NULL)
                """
            ),
            {"name": name, "perms": json.dumps(perms, ensure_ascii=False)},
        )

    # 2. 按角色给每个子菜单授权（先删旧的，再种新的，保证幂等）
    for role_code, grants in ROLE_GRANTS.items():
        for menu_name, marks in grants.items():
            import json
            # 删除该角色×该菜单的旧授权（容器 /scan 上的旧授权也一并清掉，避免冗余）
            bind.execute(
                sa.text(
                    """
                    DELETE FROM soc_role_menus
                    WHERE role_id = (SELECT id FROM soc_roles WHERE code = :code)
                      AND menu_id IN (
                          SELECT id FROM soc_menus
                          WHERE name = :mname AND parent_id =
                              (SELECT id FROM soc_menus WHERE path = '/scan' AND parent_id IS NULL)
                      )
                    """
                ),
                {"code": role_code, "mname": menu_name},
            )
            # 种新授权
            bind.execute(
                sa.text(
                    """
                    INSERT INTO soc_role_menus (role_id, menu_id, permissions)
                    SELECT r.id, m.id, CAST(:perms AS jsonb)
                    FROM soc_roles r, soc_menus m
                    WHERE r.code = :code AND m.name = :mname
                      AND m.parent_id = (SELECT id FROM soc_menus WHERE path = '/scan' AND parent_id IS NULL)
                      AND NOT EXISTS (
                          SELECT 1 FROM soc_role_menus rm
                          WHERE rm.role_id = r.id AND rm.menu_id = m.id
                      )
                    """
                ),
                {
                    "code": role_code,
                    "mname": menu_name,
                    "perms": json.dumps(marks, ensure_ascii=False),
                },
            )


def downgrade() -> None:
    bind = op.get_bind()
    # 子菜单 permissions 清空回 []（保留 role_menus，不破坏审计）
    for name in CHILD_PERMS:
        bind.execute(
            sa.text(
                """
                UPDATE soc_menus
                SET permissions = '[]'::jsonb
                WHERE name = :name
                  AND parent_id = (SELECT id FROM soc_menus WHERE path = '/scan' AND parent_id IS NULL)
                """
            ),
            {"name": name},
        )
