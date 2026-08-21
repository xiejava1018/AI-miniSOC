"""X1 权限矩阵：种 operator / viewer / auditor 三个角色（PRD P3 §X1）

down_revision: f2a3b4c5d6e7
revision     : g1h2i3j4k5l6

纯 SQL 实现：避免 Python 状态变量 + INSERT 后回读 SELECT（—sql dry-run 会
NoneType.scalar()）。所有 INSERT 都在 SQL 内部用子查询拿 id。

仅做 P3 相关菜单授权（资产列表/资产对账/数据健康/报告列表/EOL 覆盖）。
全菜单权限属于 P0/P1，按 PRD X1 拆成多个 PR 分批做。

角色定义（与 app/models/role.py RoleCode 对齐）：
  admin     - 已存在，全权限（不动）
  operator  - 资产读+写、对账 reconcile/resolve、报告 generate/trigger、EOL 覆盖
  viewer    - 仅 view 类按钮
  auditor   - 与 viewer 相同 + 「审计日志」菜单可访问（菜单授权本迁移不做，仅在权限里给标识）

按钮 authMark 与既有迁移保持一致：
  /asset/list          view, edit
  /asset/reconciliation view, reconcile, resolve, report（与 F1.3 一致）
  /asset/data-health    view
  /reports/list         view, generate, trigger（与 F2.2 一致）
"""
from alembic import op
import sqlalchemy as sa

revision = "g1h2i3j4k5l6"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- 1. 种子角色 ----------
    op.execute("""
        INSERT INTO soc_roles (name, code, description, is_system, is_active, created_at, updated_at)
        VALUES
            ('运维',     'operator', '运维角色：资产读写 + 对账/报告 + EOL 覆盖', true, true, NOW(), NOW()),
            ('观察者',   'viewer',   '只读：仅看资产/告警/报告/对账/数据健康',  true, true, NOW(), NOW()),
            ('审计人员', 'auditor',  '审计：只读 + 审计日志',               true, true, NOW(), NOW())
        ON CONFLICT (code) DO NOTHING
    """)

    # ---------- 2. 菜单授权 ----------
    # 注意：菜单 path 在 DB 里存的是“相对名”（如 'reconciliation'），不存
    # 完整路由 '/asset/reconciliation'。需联合父菜单 path 定位。
    # 例如「资产对账」=父='/assets' + path='reconciliation'。
    #
    # 路径参照 F1.3/F2.2 迁移的种子约定：
    #   /assets 下：list（资产列表）、reconciliation、data-health
    #   /reports 下：list（报告列表）
    menu_target = [
        # (parent_path, menu_path, operator_perms)
        ('/assets', 'list',                '["view","edit"]'),
        ('/assets', 'reconciliation',      '["view","reconcile","resolve","report"]'),
        ('/assets', 'data-health',         '["view"]'),
        ('/reports', 'list',               '["view","generate","trigger"]'),
    ]

    for parent_path, menu_path, op_perms in menu_target:
        # operator 授权
        op.execute(f"""
            INSERT INTO soc_role_menus (role_id, menu_id, permissions)
            SELECT r.id, m.id, '{op_perms}'::jsonb
            FROM soc_roles r, soc_menus p, soc_menus m
            WHERE r.code = 'operator'
              AND p.path = '{parent_path}' AND p.parent_id IS NULL
              AND m.parent_id = p.id AND m.path = '{menu_path}'
              AND NOT EXISTS (
                  SELECT 1 FROM soc_role_menus rm
                  WHERE rm.role_id = r.id AND rm.menu_id = m.id
              )
        """)

    # viewer + auditor 授权：仅 view
    # 注意：子查询 t 重新 select m.id 并命名为 menu_id（不能复用外部别名）
    op.execute("""
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, t.menu_id, '["view"]'::jsonb
        FROM soc_roles r
        CROSS JOIN (
            SELECT m.id AS menu_id
            FROM soc_menus p
            JOIN soc_menus m ON m.parent_id = p.id
            WHERE (p.path = '/assets'  AND m.path IN ('list','reconciliation','data-health'))
               OR (p.path = '/reports' AND m.path = 'list')
        ) t
        WHERE r.code IN ('viewer', 'auditor')
          AND NOT EXISTS (
              SELECT 1 FROM soc_role_menus rm
              WHERE rm.role_id = r.id AND rm.menu_id = t.menu_id
          )
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM soc_role_menus WHERE role_id IN (
            SELECT id FROM soc_roles WHERE code IN ('operator', 'viewer', 'auditor')
        )
    """)
    op.execute("DELETE FROM soc_users WHERE role_id IN (SELECT id FROM soc_roles WHERE code IN ('operator', 'viewer', 'auditor'))")
    op.execute("DELETE FROM soc_roles WHERE code IN ('operator', 'viewer', 'auditor')")