"""配置中心 v1：数据源 + 配置 schema + 变更审计 + 菜单种入（X1E-11 / 2026-09-11）

设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §4
需求依据：docs/design/2026-09-11-平台配置能力梳理与配置化方案.md §3 / §4

本迁移：
  1) soc_source_health 加可空字段 source_id（无外键约束，避免配置删除阻塞健康写入）
  2) 新建 3 张表：soc_data_sources / soc_config_schema / soc_config_change_log
  3) 部分唯一索引 uq_data_source_default_per_type（同 source_type 至多一个 is_default=true）
  4) 菜单种入：/system 下挂 dataSource / configCenter / configLogs 三个子菜单
     并授予 admin 角色相应权限（NOT EXISTS 幂等守卫；子查询取 parent_id / role_id）
  5) 业务"配置中心"无 .env 等价字段，菜单种子全内联字符串（无外部输入，无注入风险）

Revision ID: d2e3f4g5h6i7
Revises: c1d2e3f4g5h6
Create Date: 2026-09-11

⚠️ v1.2 文档曾主张合并 2 个 head —— 实测迁移图当前只有 1 个 head（c1d2e3f4g5h6），
本次迁移直接挂上去即可，无需 merge。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "d2e3f4g5h6i7"
down_revision: Union[str, Sequence[str], None] = "c1d2e3f4g5h6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------- 1) soc_source_health 加可空字段 source_id ----------------
    # 无外键约束：删除数据源不应阻塞健康写入；语义对齐见设计文档 §4.5
    op.execute(
        "ALTER TABLE soc_source_health ADD COLUMN IF NOT EXISTS source_id BIGINT"
    )

    # ---------------- 2) 新建 soc_data_sources ----------------
    op.create_table(
        "soc_data_sources",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_code", sa.String(length=64), nullable=False, unique=True),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("endpoint", sa.String(length=512), nullable=False),
        sa.Column(
            "auth_type", sa.String(length=32), nullable=False, server_default="none"
        ),
        sa.Column("auth_username", sa.String(length=200), nullable=True),
        sa.Column("auth_secret", sa.Text(), nullable=True),
        sa.Column("verify_ssl", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("retry_times", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "retry_backoff_seconds", sa.Integer(), nullable=False, server_default="2"
        ),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column(
            "config_json",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("last_test_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("last_test_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.BigInteger(), sa.ForeignKey("soc_users.id"), nullable=True),
    )
    op.create_index(
        "ix_data_source_type_enabled",
        "soc_data_sources",
        ["source_type", "enabled"],
        unique=False,
    )
    # 部分唯一索引：同 source_type 下 is_default=true 至多一行
    # PostgreSQL 支持部分索引；若不支持会报错，此时可降级为 Service 层事务实现
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_data_source_default_per_type "
        "ON soc_data_sources (source_type) WHERE is_default = true"
    )

    # ---------------- 3) 新建 soc_config_schema ----------------
    op.create_table(
        "soc_config_schema",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column(
            "value_type",
            sa.String(length=20),
            nullable=False,
            server_default="string",
        ),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column("options", JSONB(), nullable=True),
        sa.Column("validation", JSONB(), nullable=True),
        sa.Column(
            "effect_scope",
            sa.String(length=20),
            nullable=False,
            server_default="immediate",
        ),
        sa.Column("sensitive", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("group_name", sa.String(length=100), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("help_text", sa.Text(), nullable=True),
        sa.Column("editable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
        sa.UniqueConstraint("category", "key", name="uq_config_schema_category_key"),
    )

    # ---------------- 4) 新建 soc_config_change_log ----------------
    op.create_table(
        "soc_config_change_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_key", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("before_value", sa.Text(), nullable=True),
        sa.Column("after_value", sa.Text(), nullable=True),
        sa.Column("changed_fields", JSONB(), nullable=True),
        sa.Column("operator_id", sa.BigInteger(), sa.ForeignKey("soc_users.id"), nullable=True),
        sa.Column("operator_ip", sa.String(length=64), nullable=True),
        sa.Column("result", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("NOW()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_config_change_log_type_time",
        "soc_config_change_log",
        ["target_type", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_config_change_log_operator_time",
        "soc_config_change_log",
        ["operator_id", "created_at"],
        unique=False,
    )

    # ---------------- 5) 菜单种入（设计文档 §6.5 全 SQL 子查询写法）----------------
    # 子菜单 path 用相对名 / component 用带前导斜杠的实际路径 / icon 用 ri:*
    # / permissions JSONB 必填；parent_id 一律用子查询取，避免硬编码（/system 实际 id=5，但不要写死）
    op.execute("""
        INSERT INTO soc_menus (parent_id, name, title, path, icon, component, sort_order, is_visible, permissions)
        SELECT p.id, v.name, v.title, v.path, v.icon, v.component, v.sort_order, true, CAST(v.perms AS jsonb)
        FROM (SELECT id FROM soc_menus WHERE path = '/system' AND parent_id IS NULL) p
        CROSS JOIN (VALUES
          ('dataSource',   '数据源管理', 'data-source',   'ri:database-2-line',
           '/system/data-source',   10,
           '[{"title":"查看","authMark":"view"},{"title":"新增","authMark":"add"},{"title":"编辑","authMark":"edit"},{"title":"删除","authMark":"delete"},{"title":"连接测试","authMark":"test"}]'),
          ('configCenter', '配置中心',   'config-center', 'ri:equalizer-line',
           '/system/config-center',  11,
           '[{"title":"查看","authMark":"view"},{"title":"编辑","authMark":"edit"}]'),
          ('configLogs',   '配置审计',   'config-logs',   'ri:history-line',
           '/system/config-logs',    12,
           '[{"title":"查看","authMark":"view"}]')
        ) AS v(name, title, path, icon, component, sort_order, perms)
        WHERE NOT EXISTS (
          SELECT 1 FROM soc_menus m WHERE m.name = v.name AND m.parent_id = p.id
        )
    """)

    # 授权 admin：role_id 用子查询按 code 取；soc_role_menus 只有三列，不要带 created_at
    op.execute("""
        INSERT INTO soc_role_menus (role_id, menu_id, permissions)
        SELECT r.id, m.id,
               CAST((SELECT jsonb_agg(e->>'authMark') FROM jsonb_array_elements(m.permissions) e) AS jsonb)
        FROM soc_roles r
        CROSS JOIN soc_menus m
        WHERE r.code = 'admin'
          AND m.name IN ('dataSource', 'configCenter', 'configLogs')
          AND NOT EXISTS (
            SELECT 1 FROM soc_role_menus rm WHERE rm.role_id = r.id AND rm.menu_id = m.id
          )
    """)


def downgrade() -> None:
    # 倒序回滚：先撤授权 → 删菜单 → 删索引 → 删表 → 撤列
    op.execute("""
        DELETE FROM soc_role_menus rm
        USING soc_roles r, soc_menus m
        WHERE rm.role_id = r.id AND rm.menu_id = m.id
          AND r.code = 'admin'
          AND m.name IN ('dataSource', 'configCenter', 'configLogs')
    """)
    op.execute("""
        DELETE FROM soc_menus
        WHERE name IN ('dataSource', 'configCenter', 'configLogs')
    """)

    op.drop_index("ix_config_change_log_operator_time", table_name="soc_config_change_log")
    op.drop_index("ix_config_change_log_type_time", table_name="soc_config_change_log")
    op.drop_table("soc_config_change_log")

    op.drop_table("soc_config_schema")

    op.execute("DROP INDEX IF EXISTS uq_data_source_default_per_type")
    op.drop_index("ix_data_source_type_enabled", table_name="soc_data_sources")
    op.drop_table("soc_data_sources")

    op.execute("ALTER TABLE soc_source_health DROP COLUMN IF EXISTS source_id")