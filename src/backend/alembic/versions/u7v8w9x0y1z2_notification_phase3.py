"""OH-NOT-F2 Phase 3：FK 补全 + 邮件模板表 + 投递日志菜单

1. dispatch_logs.notification_id FK → soc_notifications(id) ON DELETE SET NULL
   （防御性先置空孤儿行，再加约束 — Phase 1 测试清理曾留孤儿）
2. soc_email_templates：DB 覆盖内置模板（type 唯一，enabled 控制）
3. 菜单「投递日志」(admin) 挂系统管理 — observability

Revision ID: u7v8w9x0y1z2
Revises: t6u7v8w9x0y1
Create Date: 2026-10-07
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "u7v8w9x0y1z2"
down_revision: Union[str, Sequence[str], None] = "t6u7v8w9x0y1"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # ---- 1. FK 补全（先防御性清孤儿）----
    bind.execute(sa.text("""
        UPDATE soc_notification_dispatch_logs d
        SET notification_id = NULL,
            error_text = COALESCE(d.error_text, '') ||
                E'\n[phase3-fk-cleanup] orphan notification_id nulled'
        WHERE d.notification_id IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM soc_notifications n WHERE n.id = d.notification_id)
    """))
    bind.execute(sa.text("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_soc_dispatch_notification'
            ) THEN
                ALTER TABLE soc_notification_dispatch_logs
                    ADD CONSTRAINT fk_soc_dispatch_notification
                    FOREIGN KEY (notification_id) REFERENCES soc_notifications(id)
                    ON DELETE SET NULL;
            END IF;
        END$$
    """))

    # ---- 2. 邮件模板覆盖表 ----
    bind.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS soc_email_templates (
            id           UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
            type         VARCHAR(64) NOT NULL UNIQUE,
            subject_tmpl TEXT NOT NULL,
            text_tmpl    TEXT NOT NULL,
            html_tmpl    TEXT NOT NULL,
            enabled      BOOLEAN NOT NULL DEFAULT true,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))

    # ---- 3. 菜单「投递日志」(admin only) ----
    bind.execute(sa.text(
        "INSERT INTO soc_menus (parent_id, name, title, path, icon, sort_order, "
        "  is_visible, component, permissions) "
        "SELECT p.id, 'notificationDispatchLogs', '投递日志', 'notification-dispatch-logs', "
        "  'ri:file-list-3-line', 10, TRUE, '/system/notification-dispatch-logs', "
        "  CAST('[{\"title\": \"查看\", \"authMark\": \"view\"}]' AS jsonb) "
        "FROM (SELECT id FROM soc_menus WHERE title = '系统管理' AND parent_id IS NULL) p "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM soc_menus m WHERE m.parent_id = p.id "
        "    AND m.path = 'notification-dispatch-logs')"))

    bind.execute(sa.text(
        "INSERT INTO soc_role_menus (role_id, menu_id, permissions) "
        "SELECT r.id, m.id, CAST('[\"view\"]' AS jsonb) "
        "FROM soc_roles r "
        "JOIN soc_menus p ON p.title = '系统管理' AND p.parent_id IS NULL "
        "JOIN soc_menus m ON m.parent_id = p.id "
        "     AND m.path = 'notification-dispatch-logs' "
        "WHERE r.code = 'admin' "
        "  AND NOT EXISTS (SELECT 1 FROM soc_role_menus rm "
        "                  WHERE rm.role_id = r.id AND rm.menu_id = m.id)"))


def downgrade() -> None:
    bind = op.get_bind()
    # 菜单
    bind.execute(sa.text(
        "DELETE FROM soc_role_menus rm USING soc_menus m "
        "WHERE rm.menu_id = m.id AND m.path = 'notification-dispatch-logs'"))
    bind.execute(sa.text(
        "DELETE FROM soc_menus WHERE path = 'notification-dispatch-logs'"))
    # 模板表
    bind.execute(sa.text("DROP TABLE IF EXISTS soc_email_templates"))
    # FK
    bind.execute(sa.text(
        "ALTER TABLE soc_notification_dispatch_logs "
        "DROP CONSTRAINT IF EXISTS fk_soc_dispatch_notification"))
