"""删除 soc_config_change_log：配置变更审计合并到 soc_audit_logs

背景
----
配置中心 v1（X1E-11）引入了独立的配置审计表 soc_config_change_log +
独立页面「配置审计」/system/config-logs。平台本来已有一套审计体系
（soc_audit_logs + @log_audit 装饰器 + log_hash/prev_log_hash 防篡改链）。

两套并行带来的真实问题：
1. data_source 的写操作**完全不在 hash 链审计中** —— 绕开了防篡改保护，
   与 CLAUDE.md「取证级审计」的设计意图相悖
2. system_config 的写操作同时散落在两张表（soc_audit_logs 2 行、
   soc_config_change_log 若干），口径不一致
3. 两套 service（AuditLogService / ConfigAuditService）+ 两个页面 +
   两套 API，维护成本翻倍而语义重叠

本次变更
--------
- ConfigAuditService.log() 改为内部转调 AuditLogService.create_audit_log()，
  data_source_service.py 的 6 个调用点（create/update/delete/enable/
  set_default/test）零改动，审计自动进入 hash 链
- 配置变更在 soc_audit_logs 中用 resource_type='data_source' 区分，
  既有的「审计日志」页面（含 ArtSearchBar 富搜索 + 详情弹窗 + 导出 CSV）
  直接复用，功能比原「配置审计」页更全
- 删除 soc_config_change_log 表、ConfigChangeLog 模型/schema/service/router
- 删除前端 /system/config-logs 页面 + configChangeLog.ts + 菜单

数据处置
--------
表内 37 行均为 2026-09-12 配置中心上线当天的联调记录（3a 写数据源 /
3b 改 .env / 3c 迁 resolver 产生的 create/update/enable/set_default/test），
**非真实运维数据**，经用户确认可直接删除，不做迁移。
若后续需要保留，可在 upgrade 前手工执行：
    INSERT INTO soc_audit_logs (user_id, username, action, resource_type,
                                resource_name, old_values, new_values,
                                ip_address, status, created_at)
    SELECT operator_id, COALESCE(u.username,'system'), c.action, c.target_type,
           c.target_key, c.before_value::jsonb, c.after_value::jsonb,
           c.operator_ip, c.result, c.created_at
    FROM soc_config_change_log c LEFT JOIN soc_users u ON u.id = c.operator_id;
（注意：老表 before_value/after_value 是 Text，需 ::jsonb 转换，
 且不会补 log_hash —— 迁入的历史行不参与 hash 链校验）

菜单清理
--------
删除 configLogs 菜单行及其 soc_role_menus 授权（admin）。
父菜单「系统管理」下原有的「审计日志」保持不变，成为唯一审计入口。

Revision ID: f3g4h5i6j7k8
Revises: e2f3g4h5i6j7
Create Date: 2026-09-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3g4h5i6j7k8"
down_revision: Union[str, Sequence[str], None] = "e2f3g4h5i6j7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---------------- 1) 删菜单授权（先删子表，避免 FK 残留）----------------
    op.execute(
        sa.text(
            """
            DELETE FROM soc_role_menus
            WHERE menu_id IN (SELECT id FROM soc_menus WHERE name = 'configLogs')
            """
        )
    )

    # ---------------- 2) 删菜单行 ----------------
    op.execute(sa.text("DELETE FROM soc_menus WHERE name = 'configLogs'"))

    # ---------------- 3) 删表（含 operator_id → soc_users 的外键）----------------
    # DROP TABLE 会自动删除该表上的外键约束与索引，无需显式 drop_constraint。
    op.execute(sa.text("DROP TABLE IF EXISTS soc_config_change_log CASCADE"))


def downgrade() -> None:
    # ---------------- 1) 重建表结构（与 d2e3f4g5h6i7 中的定义一致）----------------
    op.create_table(
        "soc_config_change_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("target_type", sa.String(length=32), nullable=False),
        sa.Column("target_key", sa.String(length=200), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False),
        sa.Column("before_value", sa.Text(), nullable=True),
        sa.Column("after_value", sa.Text(), nullable=True),
        sa.Column("changed_fields", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column(
            "operator_id",
            sa.BigInteger(),
            sa.ForeignKey("soc_users.id"),
            nullable=True,
        ),
        sa.Column("operator_ip", sa.String(length=64), nullable=True),
        sa.Column("result", sa.String(length=16), nullable=False, server_default="success"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_config_change_log_type_time",
        "soc_config_change_log",
        ["target_type", "created_at"],
    )
    op.create_index(
        "ix_config_change_log_operator_time",
        "soc_config_change_log",
        ["operator_id", "created_at"],
    )

    # ---------------- 2) 恢复菜单行（parent 用子查询取，不硬编码 id）----------------
    op.execute(
        sa.text(
            """
            INSERT INTO soc_menus (parent_id, name, title, path, icon, component,
                                   sort_order, is_visible, permissions)
            SELECT p.id, 'configLogs', '配置审计', 'config-logs', 'ri:history-line',
                   '/system/config-logs', 12, true,
                   CAST('[{"title":"查看","authMark":"view"}]' AS jsonb)
            FROM (SELECT id FROM soc_menus
                  WHERE name = '系统管理' AND parent_id IS NULL) p
            WHERE NOT EXISTS (
                SELECT 1 FROM soc_menus m WHERE m.name = 'configLogs'
            )
            """
        )
    )

    # ---------------- 3) 恢复 admin 授权 ----------------
    op.execute(
        sa.text(
            """
            INSERT INTO soc_role_menus (role_id, menu_id, permissions)
            SELECT r.id, m.id, CAST('["view"]' AS jsonb)
            FROM soc_roles r CROSS JOIN soc_menus m
            WHERE r.code = 'admin' AND m.name = 'configLogs'
              AND NOT EXISTS (
                SELECT 1 FROM soc_role_menus rm
                WHERE rm.role_id = r.id AND rm.menu_id = m.id
              )
            """
        )
    )
