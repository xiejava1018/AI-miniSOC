"""create soc_task_registry and soc_task_runs (task observability v0.4.2 Phase 1)

Revision ID: e8f9a0b1c2d3
Revises: d7e8f9a0b1c2
Create Date: 2026-08-16 23:00:00.000000

后台任务执行可观测性 Phase 1：
- soc_task_registry：每任务一行（定义 + 当前态）
- soc_task_runs：每执行一行（真历史 + 独立进度心跳）

参考：docs/design/2026-08-16-后台任务执行可观测性梳理与方案-v0.4.md §3.1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8f9a0b1c2d3"
down_revision: Union[str, Sequence[str], None] = "d7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ENUM 类型名（SQLAlchemy native_enum=False，所以实际是 VARCHAR + CHECK，不需要 CREATE TYPE）
# 这里只在表内用 CHECK 约束

def upgrade() -> None:
    # soc_task_registry
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS soc_task_registry (
            task_key              VARCHAR(100) PRIMARY KEY,
            task_name             VARCHAR(200) NOT NULL,
            task_type             VARCHAR(20)  NOT NULL,
            owner_module          VARCHAR(200),
            schedule_expr         VARCHAR(100),
            expected_interval_s   INTEGER,
            timeout_s             INTEGER NOT NULL DEFAULT 360,
            enabled               BOOLEAN NOT NULL DEFAULT TRUE,
            current_run_id        UUID,
            lock_owner            VARCHAR(200),
            last_run_at           TIMESTAMPTZ,
            last_status           VARCHAR(20),
            last_error            TEXT,
            last_duration_ms      INTEGER,
            last_stats            JSONB,
            consecutive_failures  INTEGER NOT NULL DEFAULT 0,
            total_runs            BIGINT NOT NULL DEFAULT 0,
            created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_task_registry_type
                CHECK (task_type IN ('scheduled', 'async', 'thread', 'watchdog')),
            CONSTRAINT ck_task_registry_timeout
                CHECK (timeout_s >= 30)
        )
        """
    )

    # soc_task_runs
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS soc_task_runs (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_key            VARCHAR(100) NOT NULL,
            trigger             VARCHAR(20) NOT NULL,
            started_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at         TIMESTAMPTZ,
            status              VARCHAR(20) NOT NULL,
            duration_ms         INTEGER,
            error_text          TEXT,
            stats_json          JSONB,
            total               INTEGER,
            processed           INTEGER,
            percent             INTEGER,
            last_progress_at    TIMESTAMPTZ,
            correlation_id      VARCHAR(100),
            host                VARCHAR(200),
            triggered_by_user   VARCHAR(200),
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT ck_task_runs_trigger
                CHECK (trigger IN ('scheduled', 'manual', 'api', 'replay', 'startup', 'watchdog')),
            CONSTRAINT ck_task_runs_status
                CHECK (status IN ('pending', 'running', 'success', 'failed', 'timeout',
                                  'skipped', 'zombie', 'unknown')),
            CONSTRAINT fk_task_runs_registry
                FOREIGN KEY (task_key) REFERENCES soc_task_registry(task_key)
                ON DELETE SET NULL
        )
        """
    )
    # registry.current_run_id -> runs.id（事后加，避免建表顺序环）
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'fk_task_registry_current_run'
            ) THEN
                ALTER TABLE soc_task_registry
                ADD CONSTRAINT fk_task_registry_current_run
                FOREIGN KEY (current_run_id) REFERENCES soc_task_runs(id)
                ON DELETE SET NULL;
            END IF;
        END$$;
        """
    )

    # 索引
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_task_runs_taskkey_started
        ON soc_task_runs (task_key, started_at DESC)
        """
    )
    # 部分索引：仅 running 行参与 zombie 扫描
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_task_runs_running_partial
        ON soc_task_runs (started_at)
        WHERE status = 'running'
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_task_runs_status_started
        ON soc_task_runs (status, started_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_task_runs_correlation
        ON soc_task_runs (correlation_id)
        WHERE correlation_id IS NOT NULL
        """
    )

    # updated_at 自动维护
    op.execute(
        """
        CREATE OR REPLACE FUNCTION trg_task_registry_set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS tg_task_registry_updated ON soc_task_registry;
        CREATE TRIGGER tg_task_registry_updated
        BEFORE UPDATE ON soc_task_registry
        FOR EACH ROW EXECUTE FUNCTION trg_task_registry_set_updated_at();
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS soc_task_runs CASCADE")
    op.execute("DROP TABLE IF EXISTS soc_task_registry CASCADE")
    op.execute("DROP FUNCTION IF EXISTS trg_task_registry_set_updated_at() CASCADE")
