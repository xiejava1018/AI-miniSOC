"""asset reconciliation and data health (P3 F1.3)

新增 soc_asset_reconciliations（台账 vs 实际网络的差异记录），
并种入「资产对账」与「数据健康」两个菜单。

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-08-21

幂等约定（与本项目既有迁移一致）：建表用 IF NOT EXISTS，菜单用 NOT EXISTS 子查询，
父菜单按 path 动态解析而非硬编码 id——曾经硬编码 parent_id 导致空库重建撞外键。
"""

from alembic import op

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_asset_reconciliations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL,
            task_id UUID REFERENCES soc_sync_tasks(id) ON DELETE SET NULL,
            asset_id UUID REFERENCES soc_assets(id) ON DELETE CASCADE,
            reconciliation_type VARCHAR(20) NOT NULL,
            details JSONB NOT NULL DEFAULT '{}',
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            resolved_by VARCHAR(255),
            resolved_at TIMESTAMP WITH TIME ZONE,
            resolve_note TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_soc_asset_recon_run
            ON soc_asset_reconciliations (run_id, status)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_soc_asset_recon_asset
            ON soc_asset_reconciliations (asset_id)
    """)
    # 待处理队列：数据健康页的红点计数走这条 partial index
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_soc_asset_recon_pending
            ON soc_asset_reconciliations (created_at)
            WHERE status = 'pending'
    """)

    # ---- 菜单：资产对账（挂在「资产管理」/assets 下，与合规基线同级）
    op.execute("""
        INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                               sort_order, is_visible, permissions, created_at, updated_at)
        SELECT p.id, '资产对账', '资产对账', 'reconciliation', 'ri:git-compare-line',
               '/asset/reconciliation/index', 5, TRUE,
               '[{"title":"查看","authMark":"view"},
                 {"title":"执行对账","authMark":"reconcile"},
                 {"title":"处理差异","authMark":"resolve"},
                 {"title":"AI 报告","authMark":"report"}]'::jsonb,
               NOW(), NOW()
        FROM soc_menus p
        WHERE p.path = '/assets' AND p.parent_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM soc_menus WHERE path = 'reconciliation' AND parent_id = p.id
          )
    """)
    op.execute("""
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, m.id, '["view","reconcile","resolve","report"]'::jsonb
        FROM soc_roles r
        JOIN soc_menus m ON m.path = 'reconciliation'
        JOIN soc_menus p ON p.id = m.parent_id AND p.path = '/assets'
        WHERE r.code = 'admin'
          AND NOT EXISTS (
              SELECT 1 FROM soc_role_menus rm WHERE rm.role_id = r.id AND rm.menu_id = m.id
          )
    """)

    # ---- 菜单：数据健康（同样挂 /assets 下；三层健康的统一入口）
    op.execute("""
        INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                               sort_order, is_visible, permissions, created_at, updated_at)
        SELECT p.id, '数据健康', '数据健康', 'data-health', 'ri:heart-pulse-line',
               '/asset/data-health/index', 6, TRUE,
               '[{"title":"查看","authMark":"view"}]'::jsonb,
               NOW(), NOW()
        FROM soc_menus p
        WHERE p.path = '/assets' AND p.parent_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM soc_menus WHERE path = 'data-health' AND parent_id = p.id
          )
    """)
    op.execute("""
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, m.id, '["view"]'::jsonb
        FROM soc_roles r
        JOIN soc_menus m ON m.path = 'data-health'
        JOIN soc_menus p ON p.id = m.parent_id AND p.path = '/assets'
        WHERE r.code = 'admin'
          AND NOT EXISTS (
              SELECT 1 FROM soc_role_menus rm WHERE rm.role_id = r.id AND rm.menu_id = m.id
          )
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM soc_role_menus WHERE menu_id IN (
            SELECT m.id FROM soc_menus m
            JOIN soc_menus p ON p.id = m.parent_id AND p.path = '/assets'
            WHERE m.path IN ('reconciliation', 'data-health')
        )
    """)
    op.execute("""
        DELETE FROM soc_menus WHERE id IN (
            SELECT m.id FROM soc_menus m
            JOIN soc_menus p ON p.id = m.parent_id AND p.path = '/assets'
            WHERE m.path IN ('reconciliation', 'data-health')
        )
    """)
    op.execute("DROP INDEX IF EXISTS idx_soc_asset_recon_pending")
    op.execute("DROP INDEX IF EXISTS idx_soc_asset_recon_asset")
    op.execute("DROP INDEX IF EXISTS idx_soc_asset_recon_run")
    op.execute("DROP TABLE IF EXISTS soc_asset_reconciliations")
