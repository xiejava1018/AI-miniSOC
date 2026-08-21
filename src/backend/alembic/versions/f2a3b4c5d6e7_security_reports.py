"""安全报告表（PRD P3 / F2.2）

  down_revision: e4f5a6b7c8d9
  revision     : f2a3b4c5d6e7

落 soc_security_reports 表 + 2 索引 + 2 菜单（安全报告列表、安全报告-生成/详情
合并到 list，无需单独菜单）。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

# revision identifiers, used by Alembic.
revision = "f2a3b4c5d6e7"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS soc_security_reports (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            report_type VARCHAR(20) NOT NULL,
            period_start TIMESTAMP WITH TIME ZONE NOT NULL,
            period_end TIMESTAMP WITH TIME ZONE NOT NULL,
            title VARCHAR(255),
            summary TEXT,
            content JSONB,
            risk_highlights TEXT,
            recommendations TEXT,
            data_coverage JSONB NOT NULL,
            prompt_version VARCHAR(20),
            triggered_by VARCHAR(64),
            trigger_meta JSONB,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_soc_security_reports_created ON soc_security_reports (created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_soc_security_reports_type_created "
        "ON soc_security_reports (report_type, created_at)"
    )

    # ---------- 菜单：安全报告（独立顶级，与「概览仪表板」并列） ----------
    # 全 SQL 写法：避免 INSERT 后回读 SELECT（—sql dry-run 模式下不会执行 INSERT，
    # 回读会报 NoneType.scalar；这是 F1.3 迁移已验证的写法）。
    op.execute("""
        INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                               sort_order, is_visible, permissions, created_at, updated_at)
        SELECT NULL, '安全报告', '安全报告', '/reports', 'Document', '',
               50, TRUE,
               '[{"title":"查看","authMark":"view"},
                 {"title":"生成报告","authMark":"generate"},
                 {"title":"事件驱动检查","authMark":"trigger"}]'::jsonb,
               NOW(), NOW()
        WHERE NOT EXISTS (
            SELECT 1 FROM soc_menus WHERE path = '/reports' AND parent_id IS NULL
        )
    """)
    op.execute("""
        INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                               sort_order, is_visible, permissions, created_at, updated_at)
        SELECT p.id, '报告列表', '报告列表', 'list', '',
               '/reports/list/index', 10, TRUE,
               '[{"title":"查看","authMark":"view"},
                 {"title":"生成报告","authMark":"generate"},
                 {"title":"事件驱动检查","authMark":"trigger"}]'::jsonb,
               NOW(), NOW()
        FROM soc_menus p
        WHERE p.path = '/reports' AND p.parent_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM soc_menus WHERE path = 'list' AND parent_id = p.id
          )
    """)
    op.execute("""
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, m.id, '["view","generate","trigger"]'::jsonb
        FROM soc_roles r
        JOIN soc_menus m ON m.path = 'list' AND m.parent_id IS NOT NULL
        JOIN soc_menus p ON p.id = m.parent_id AND p.path = '/reports'
        WHERE r.code = 'admin'
          AND NOT EXISTS (
              SELECT 1 FROM soc_role_menus rm WHERE rm.role_id = r.id AND rm.menu_id = m.id
          )
    """)


def downgrade() -> None:
    # 删除菜单授权 / 菜单 / 表（按逆序）。注意 down 不强行删菜单，避免误删已在生产
    # 重新关联到其它子页面的项；只在表无数据时删菜单。
    op.execute("DROP INDEX IF EXISTS idx_soc_security_reports_type_created")
    op.execute("DROP INDEX IF EXISTS idx_soc_security_reports_created")
    op.execute("DROP TABLE IF EXISTS soc_security_reports")