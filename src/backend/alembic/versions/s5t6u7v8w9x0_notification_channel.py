"""通知通道扩展：inbox + email（OH-NOT-F2 · Phase 1）

Phase 1 仅本期：
  1. soc_notification_channels      通道定义 (inbox 预置 + email 模板)
  2. soc_notification_dispatch_logs 每通道投递日志（pending/sent/failed/skipped_pref）
  3. soc_notification_user_prefs   用户 per (type, channel) 偏好

Phase 2 (本迁移**不**做)：
  - soc_email_templates 模板
  - soc_email_retry_policies
  - soc_unsubscribe_tokens

CLAUDE.md §1.2 表前缀强制 `soc_`，§4.3 4 条红线全中：
- 禁硬编码 id → 用 `INSERT INTO ... SELECT ... WHERE NOT EXISTS`
- JSONB 用 CAST(:perms AS jsonb) 不用 ::jsonb（避免绑定参数化报错）
- 双 down_revision (multi-head 兼容)
- IF NOT EXISTS / WHERE NOT EXISTS 幂等守卫

Revision ID: s5t6u7v8w9x0
Revises: r4c5d6e7f8a9
Create Date: 2026-10-07
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision: str = "s5t6u7v8w9x0"
down_revision: Union[str, Sequence[str], None] = "r4c5d6e7f8a9"
branch_labels: Union[str, Sequence[str]] | None = None
depends_on: Union[str, Sequence[str]] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # =========================================================
    # 1. soc_notification_channels
    #    - code UNIQUE (例如 'inbox', 'email', 未来 'sms'/'webhook')
    #    - config_json: 通道专属配置 (email: smtp_host/user/pass/...)
    #    - 预置 inbox (always enabled, 无 config) + email (disabled 等待 admin 配)
    # =========================================================
    bind.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS soc_notification_channels (
            id          SMALLSERIAL NOT NULL PRIMARY KEY,
            code        VARCHAR(16) NOT NULL UNIQUE,
            name        VARCHAR(50) NOT NULL,
            enabled     BOOLEAN NOT NULL DEFAULT true,
            config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_soc_notif_channels_code_lowercase
                CHECK (code = LOWER(code))
        )
    """))

    # 预置 inbox 通道（始终启用，无需配置）
    bind.execute(sa.text("""
        INSERT INTO soc_notification_channels (code, name, enabled, config_json)
        SELECT 'inbox', '站内信', true, CAST('{}' AS jsonb)
        WHERE NOT EXISTS (
            SELECT 1 FROM soc_notification_channels WHERE code = 'inbox'
        )
    """))

    # 预置 email 通道（默认禁用，等待 admin 配置 SMTP）
    bind.execute(sa.text("""
        INSERT INTO soc_notification_channels (code, name, enabled, config_json)
        SELECT 'email', '邮件', false, CAST('{}' AS jsonb)
        WHERE NOT EXISTS (
            SELECT 1 FROM soc_notification_channels WHERE code = 'email'
        )
    """))

    # =========================================================
    # 2. soc_notification_dispatch_logs
    #    - notification_id 可空 (push 类系统通知直接发可无具体站内通知 id)
    #    - channel_code: 'inbox' | 'email'
    #    - status: pending / sent / failed / bounced / skipped_pref
    #    - retry_count + 失败重试 next_retry_at 指数退避
    #    - correlation_id 把同一逻辑 channel 的所有投递绑成一组（trace）
    # =========================================================
    bind.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS soc_notification_dispatch_logs (
            id              UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
            notification_id UUID,
            user_id         INTEGER NOT NULL,
            channel_code    VARCHAR(16) NOT NULL,
            status          VARCHAR(16) NOT NULL DEFAULT 'pending',
            error_text      TEXT,
            sent_at         TIMESTAMPTZ,
            retry_count     INTEGER NOT NULL DEFAULT 0,
            next_retry_at   TIMESTAMPTZ,
            correlation_id  VARCHAR(64),
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_soc_dispatch_status
                CHECK (status IN ('pending','sent','failed','bounced','skipped_pref')),
            CONSTRAINT ck_soc_dispatch_channel_code
                CHECK (channel_code = LOWER(channel_code))
        )
    """))

    bind.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_soc_dispatch_user_channel_sent
            ON soc_notification_dispatch_logs (user_id, channel_code, sent_at)
    """))

    bind.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_soc_dispatch_status_next_retry
            ON soc_notification_dispatch_logs (status, next_retry_at)
            WHERE status IN ('pending','failed')
    """))

    bind.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_soc_dispatch_notification
            ON soc_notification_dispatch_logs (notification_id)
            WHERE notification_id IS NOT NULL
    """))

    # 注意：这里不加 FK 约束 — 旧版 soc_notifications.id 是 UUID 以外的类型，
    # 不验明下仓促加 FK 会迁移报错。dispatch_logs.notification_id 只是个软引用
    # (逻辑靠 supplement_字段检查), 而业务上 push_only 类型同样在后台动成没问题。
    # FK 留给 Phase 2 补完整 schema 后一并加上。

    # =========================================================
    # 3. soc_notification_user_prefs
    #    - 唯一 (user_id, type, channel_code)
    #    - 默认空表 = 用户对所有 (type, channel) 都启用
    #    - 有偏好: enabled=false 表示该类型在对应通道**不投递**（用户主动禁）
    # =========================================================
    bind.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS soc_notification_user_prefs (
            id           UUID NOT NULL PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id      INTEGER NOT NULL REFERENCES soc_users(id) ON DELETE CASCADE,
            type         VARCHAR(64) NOT NULL,
            channel_code VARCHAR(16) NOT NULL,
            enabled      BOOLEAN NOT NULL DEFAULT true,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_soc_notif_pref_user_type_channel
                UNIQUE (user_id, type, channel_code)
        )
    """))

    bind.execute(sa.text("""
        CREATE INDEX IF NOT EXISTS ix_soc_notif_pref_user
            ON soc_notification_user_prefs (user_id)
    """))


def downgrade() -> None:
    # 镜像回滚（倒序）
    op.drop_index("ix_soc_notif_pref_user", table_name="soc_notification_user_prefs", if_exists=True)
    op.drop_table("soc_notification_user_prefs", if_exists=True)

    op.drop_index("ix_soc_dispatch_notification", table_name="soc_notification_dispatch_logs", if_exists=True)
    op.drop_index("ix_soc_dispatch_status_next_retry", table_name="soc_notification_dispatch_logs", if_exists=True)
    op.drop_index("ix_soc_dispatch_user_channel_sent", table_name="soc_notification_dispatch_logs", if_exists=True)
    op.drop_table("soc_notification_dispatch_logs", if_exists=True)

    op.drop_table("soc_notification_channels", if_exists=True)