"""F3.1 变更影响分析菜单（PRD P3 / F3.1）

down_revision: g1h2i3j4k5l6
revision     : h2i3j4k5l6m7

只种菜单 + admin/operator 授权（viewer 不给 —— 变更评估是写操作前置动作，
只读角色不需要；后端也是 require_role("admin","operator")）。

纯 SQL 幂等写法（F1.3 已验证）：
  - INSERT ... SELECT + NOT EXISTS，不用 Python 状态变量
  - 不在 INSERT 后回读 .scalar()（--sql dry-run 下会 NoneType 炸）
  - 父菜单解析不到时静默插 0 行 → upgrade 后必须查表确认

菜单约定（踩过两次坑）：
  soc_menus 列名已对照真库确认：是 is_visible（不是 is_hidden，语义相反），
  且有 title 列（大量旧数据为 NULL 但新增应补上）
"""
from alembic import op

revision = "h2i3j4k5l6m7"
down_revision = "g1h2i3j4k5l6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------- 1. 菜单 ----------
    # 挂在 /assets 父菜单下，与「资产对账」「数据健康」并列
    op.execute("""
        INSERT INTO soc_menus
            (name, title, path, component, parent_id, icon, sort_order, is_visible,
             permissions, created_at, updated_at)
        SELECT
            '变更影响分析',
            '变更影响分析',
            'impact-analysis',
            '/asset/impact-analysis/index',
            p.id,
            '&#xe6a0;',
            7,
            true,
            '[{"title":"查看","authMark":"view"},{"title":"发起分析","authMark":"analyze"}]'::jsonb,
            NOW(), NOW()
        FROM soc_menus p
        WHERE p.path = '/assets' AND p.parent_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM soc_menus m
              WHERE m.path = 'impact-analysis' AND m.parent_id = p.id
          )
    """)

    # ---------- 2. admin 授权 ----------
    op.execute("""
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, m.id, '["view","analyze"]'::jsonb
        FROM soc_roles r
        CROSS JOIN soc_menus m
        JOIN soc_menus p ON p.id = m.parent_id
        WHERE r.code = 'admin'
          AND m.path = 'impact-analysis'
          AND p.path = '/assets'
          AND NOT EXISTS (
              SELECT 1 FROM soc_role_menus rm
              WHERE rm.role_id = r.id AND rm.menu_id = m.id
          )
    """)

    # ---------- 3. operator 授权 ----------
    op.execute("""
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, m.id, '["view","analyze"]'::jsonb
        FROM soc_roles r
        CROSS JOIN soc_menus m
        JOIN soc_menus p ON p.id = m.parent_id
        WHERE r.code = 'operator'
          AND m.path = 'impact-analysis'
          AND p.path = '/assets'
          AND NOT EXISTS (
              SELECT 1 FROM soc_role_menus rm
              WHERE rm.role_id = r.id AND rm.menu_id = m.id
          )
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM soc_role_menus
        WHERE menu_id IN (
            SELECT m.id FROM soc_menus m
            JOIN soc_menus p ON p.id = m.parent_id
            WHERE m.path = 'impact-analysis' AND p.path = '/assets'
        )
    """)
    op.execute("""
        DELETE FROM soc_menus
        WHERE path = 'impact-analysis'
          AND parent_id = (SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL)
    """)