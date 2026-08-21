"""create soc_knowledge_base + seed knowledge menu (P3/F2.3)

Revision ID: b1c2d3e4f5a6
Revises: a7f8e9d0c1b2
Create Date: 2026-08-21 16:00:00.000000

P3 F2.3（PRD ai-asset-management-prd.md v1.2.1）：
- 新表 soc_knowledge_base（运维知识库：incident_summary/manual 来源、
  老化字段 last_validated_at/confidence_score/review_status）
- 种子菜单：顶级「知识库」（dashboard 式单页：path=/knowledge +
  component 直指页面），授权给 admin 角色
幂等：表用 IF NOT EXISTS，菜单/授权用 WHERE NOT EXISTS。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a7f8e9d0c1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MENU_PERMISSIONS = sa.text(
    """'[
    {"title": "查看", "authMark": "view"},
    {"title": "新增", "authMark": "add"},
    {"title": "编辑", "authMark": "edit"},
    {"title": "验证", "authMark": "validate"},
    {"title": "AI 提取", "authMark": "auto_extract"}
]'::jsonb"""
)


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_knowledge_base (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title VARCHAR(255) NOT NULL,
            content TEXT NOT NULL,
            category VARCHAR(50),
            source_type VARCHAR(50),
            source_id VARCHAR(100),
            tags TEXT,
            last_validated_at TIMESTAMPTZ,
            confidence_score SMALLINT DEFAULT 70,
            review_status VARCHAR(20) DEFAULT 'active',
            created_by VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS idx_soc_kb_category ON soc_knowledge_base (category)",
        "CREATE INDEX IF NOT EXISTS idx_soc_kb_review_status ON soc_knowledge_base (review_status)",
        "CREATE INDEX IF NOT EXISTS idx_soc_kb_source ON soc_knowledge_base (source_type, source_id)",
        "CREATE INDEX IF NOT EXISTS idx_soc_kb_updated ON soc_knowledge_base (updated_at)",
    ):
        op.execute(idx_sql)

    # 种子菜单（顶级单页，dashboard 式）
    op.execute(
        sa.text(
            """
            INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                                   sort_order, is_visible, permissions, created_at, updated_at)
            SELECT NULL, '知识库', '知识库', '/knowledge', 'ri:book-2-line',
                   '/knowledge/list/index', 65, TRUE,
                   """
            + str(MENU_PERMISSIONS)
            + """,
                   now(), now()
            WHERE NOT EXISTS (
                SELECT 1 FROM soc_menus WHERE path = '/knowledge' AND parent_id IS NULL
            )
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO soc_role_menus (role_id, menu_id, permissions)
            SELECT r.id, m.id, '["view","add","edit","validate","auto_extract"]'::jsonb
            FROM soc_roles r
            JOIN soc_menus m ON m.path = '/knowledge' AND m.parent_id IS NULL
            WHERE r.code = 'admin'
              AND NOT EXISTS (
                  SELECT 1 FROM soc_role_menus rm
                  WHERE rm.role_id = r.id AND rm.menu_id = m.id
              )
            """
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("""
            DELETE FROM soc_role_menus
            WHERE menu_id IN (SELECT id FROM soc_menus WHERE path = '/knowledge' AND parent_id IS NULL)
        """)
    )
    op.execute(sa.text("DELETE FROM soc_menus WHERE path = '/knowledge' AND parent_id IS NULL"))
    op.execute("DROP TABLE IF EXISTS soc_knowledge_base CASCADE")
