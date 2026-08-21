"""F3.3 合规基线：巡检批次表 + 问题项表

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-08-21

设计说明：
- 仅落 fail/unknown 明细（pass 计数在 runs.stats.per_rule 中），控制表体积
- 规则库本身在 configs/compliance_rules.yaml（git 版本管理），不入库；
  巡检结果记录 ruleset_version + 每条 rule_version，审计可回溯到具体规则文本
- 幂等：IF NOT EXISTS，可重复执行
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'd3e4f5a6b7c8'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_compliance_runs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            ruleset_version VARCHAR(20) NOT NULL,
            ruleset_name VARCHAR(100),
            rules_total INTEGER NOT NULL DEFAULT 0,
            assets_total INTEGER NOT NULL DEFAULT 0,
            assets_in_scope INTEGER NOT NULL DEFAULT 0,
            pass_count INTEGER NOT NULL DEFAULT 0,
            fail_count INTEGER NOT NULL DEFAULT 0,
            unknown_count INTEGER NOT NULL DEFAULT 0,
            compliance_rate INTEGER,
            coverage_rate INTEGER,
            stats JSONB,
            triggered_by VARCHAR(100),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_soc_compliance_runs_created
        ON soc_compliance_runs (created_at DESC)
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_compliance_findings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            run_id UUID NOT NULL REFERENCES soc_compliance_runs(id) ON DELETE CASCADE,
            asset_id UUID NOT NULL REFERENCES soc_assets(id) ON DELETE CASCADE,
            rule_id VARCHAR(32) NOT NULL,
            rule_version INTEGER NOT NULL,
            rule_title VARCHAR(200),
            category VARCHAR(32),
            severity VARCHAR(16),
            status VARCHAR(16) NOT NULL,
            reason TEXT,
            evidence JSONB,
            ai_remediation TEXT,
            ai_model VARCHAR(50),
            ai_prompt_version VARCHAR(40),
            ai_generated_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    for name, cols in [
        ("idx_soc_compliance_findings_run", "run_id, status"),
        ("idx_soc_compliance_findings_asset", "asset_id"),
        ("idx_soc_compliance_findings_rule", "rule_id"),
    ]:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON soc_compliance_findings ({cols})")

    # 菜单：挂在「资产管理」(/assets) 下，与资产概览/列表同级
    # 子菜单 path 用相对路径（对齐现有 overview/list/detail 约定）
    op.execute("""
        INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                               sort_order, is_visible, permissions, created_at, updated_at)
        SELECT p.id, '合规基线', '合规基线', 'compliance', 'ri:shield-check-line',
               '/asset/compliance/index', 4, TRUE,
               '[{"title":"查看","authMark":"view"},
                 {"title":"执行巡检","authMark":"check"},
                 {"title":"AI 解读","authMark":"interpret"}]'::jsonb,
               NOW(), NOW()
        FROM soc_menus p
        WHERE p.path = '/assets' AND p.parent_id IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM soc_menus WHERE path = 'compliance' AND parent_id = p.id
          )
    """)
    op.execute("""
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, m.id, '["view","check","interpret"]'::jsonb
        FROM soc_roles r
        JOIN soc_menus m ON m.path = 'compliance'
        JOIN soc_menus p ON p.id = m.parent_id AND p.path = '/assets'
        WHERE r.code = 'admin'
          AND NOT EXISTS (
              SELECT 1 FROM soc_role_menus rm WHERE rm.role_id = r.id AND rm.menu_id = m.id
          )
    """)


def downgrade() -> None:
    op.execute("""
        DELETE FROM soc_role_menus WHERE menu_id IN (
            SELECT m.id FROM soc_menus m JOIN soc_menus p ON p.id = m.parent_id
            WHERE m.path = 'compliance' AND p.path = '/assets'
        )
    """)
    op.execute("""
        DELETE FROM soc_menus WHERE path = 'compliance' AND parent_id IN (
            SELECT id FROM soc_menus WHERE path = '/assets' AND parent_id IS NULL
        )
    """)
    op.execute("DROP TABLE IF EXISTS soc_compliance_findings")
    op.execute("DROP TABLE IF EXISTS soc_compliance_runs")
