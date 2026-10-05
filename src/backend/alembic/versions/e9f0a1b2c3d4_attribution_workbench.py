"""OH-UI.3 确认工作台：soc_attribution_reviews + 菜单

- 表 soc_attribution_reviews：身份融合 needs_review 观测的人工裁决队列
  （pending/merged/created/dismissed；同指纹唯一 partial index 去重）
- 菜单「归属确认」挂「资产管理」(id=2) 下，sort_order=10：
  path='attribution', component='/asset/attribution-workbench/index'
  permissions: view / resolve
- 授权对齐 API：admin/operator 全量；viewer/auditor 只读
- 种子纯 SQL INSERT…SELECT + NOT EXISTS 幂等，JOIN 菜单/角色表，不硬编码 id；
  soc_role_menus 只有 role_id/menu_id/permissions 三列

Revision ID: e9f0a1b2c3d4
Revises: d8e9f0a1b2c3
Create Date: 2026-10-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_MENU_PERMS = (
    '[{"title": "查看", "authMark": "view"},'
    ' {"title": "裁决", "authMark": "resolve"}]'
)


def upgrade() -> None:
    op.create_table(
        "soc_attribution_reviews",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("review_kind", sa.String(20), nullable=False,
                  server_default="identity_conflict"),
        sa.Column("observation", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("observation_fingerprint", sa.String(64), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("sync_task_id",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("soc_sync_tasks.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("asset_id",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("soc_assets.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("candidate_asset_id",
                  sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("soc_assets.id", ondelete="SET NULL"),
                  nullable=True),
        sa.Column("best_score", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("candidates", sa.dialects.postgresql.JSONB, nullable=False,
                  server_default="[]"),
        sa.Column("candidate_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("occurrence_count", sa.Integer, nullable=False, server_default="1"),
        sa.Column("last_occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_by", sa.String(255)),
        sa.Column("resolved_at", sa.DateTime(timezone=True)),
        sa.Column("resolve_note", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        schema=None,
    )

    # 唯一 partial：同指纹同时仅一条 pending
    op.create_index(
        "idx_soc_attr_review_fp_pending", "soc_attribution_reviews",
        ["observation_fingerprint"], unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "idx_soc_attr_review_status", "soc_attribution_reviews",
        ["status", "created_at"],
    )
    op.create_index(
        "idx_soc_attr_review_candidate", "soc_attribution_reviews",
        ["candidate_asset_id"],
    )
    op.create_index(
        "idx_soc_attr_review_asset", "soc_attribution_reviews",
        ["asset_id"],
    )

    bind = op.get_bind()

    # 菜单（父=资产管理 id=2；幂等：parent+path 唯一判定）
    bind.execute(sa.text(
        "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
        "  is_visible, component, permissions) "
        "SELECT 2, '归属确认', '归属确认', 'attribution', 'ri:user-search-line', 10, "
        "  TRUE, '/asset/attribution-workbench/index', CAST(:perms AS jsonb) "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM soc_menus WHERE parent_id = 2 AND path = 'attribution')"),
        {"perms": _MENU_PERMS},
    )

    # 角色授权（JOIN 角色/菜单，不硬编码 id；幂等 NOT EXISTS）
    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[\"view\", \"resolve\"]' AS jsonb) "
        "FROM soc_roles r JOIN soc_menus m ON m.parent_id = 2 AND m.path = 'attribution' "
        "WHERE r.code IN ('admin', 'operator') "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"))
    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[\"view\"]' AS jsonb) "
        "FROM soc_roles r JOIN soc_menus m ON m.parent_id = 2 AND m.path = 'attribution' "
        "WHERE r.code IN ('viewer', 'auditor') "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM soc_role_menus rm USING soc_menus m "
        "WHERE rm.menu_id = m.id AND m.parent_id = 2 AND m.path = 'attribution'"))
    bind.execute(sa.text(
        "DELETE FROM soc_menus WHERE parent_id = 2 AND path = 'attribution'"))

    op.drop_index("idx_soc_attr_review_asset", table_name="soc_attribution_reviews")
    op.drop_index("idx_soc_attr_review_candidate", table_name="soc_attribution_reviews")
    op.drop_index("idx_soc_attr_review_status", table_name="soc_attribution_reviews")
    op.drop_index("idx_soc_attr_review_fp_pending", table_name="soc_attribution_reviews")
    op.drop_table("soc_attribution_reviews")
