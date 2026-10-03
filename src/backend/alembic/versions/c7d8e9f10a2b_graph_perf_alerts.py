"""soc_graph_perf_alerts (OH-3.7, Session #11)

图谱 P95 性能告警事件表（sysadmin 视角；不是 user-level 推送）。
- 触发条件：连续 N 轮 P95 超过阈值 + 滑窗样本数达到最低线（防冷启误报）
- 防抖：sustained_rounds 默认 3（CLAUDE.md §4.10 冷启 8s+ 教训）
- 区分 warning / critical 双级：warning=P95 超过阈值；critical=P95+max 都超

幂等：soc_graph_perf_alerts 是新表；不存在则创建，存在则跳过（IF NOT EXISTS）。

Revision ID: c7d8e9f10a2b
Revises: b6c7d8e9f0a1
Create Date: 2026-10-03
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c7d8e9f10a2b"
down_revision: Union[str, Sequence[str], None] = "b6c7d8e9f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text(
        """
        CREATE TABLE IF NOT EXISTS soc_graph_perf_alerts (
            id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            alert_type      varchar(64)  NOT NULL,
            query_type      varchar(32)  NOT NULL,
            severity        varchar(16)  NOT NULL,
            triggered_at    timestamptz  NOT NULL,
            window_size     integer      NOT NULL,
            p50_ms          numeric(10,2) NOT NULL,
            p95_ms          numeric(10,2) NOT NULL,
            max_ms          numeric(10,2) NOT NULL,
            slow_count      integer      NOT NULL,
            threshold_ms    numeric(10,2) NOT NULL,
            message         text         NOT NULL,
            resolved_at     timestamptz,
            resolved        boolean       NOT NULL DEFAULT FALSE,
            metadata        jsonb         NOT NULL DEFAULT '{}'::jsonb,
            created_at      timestamptz  NOT NULL DEFAULT now()
        )
        """
    ))
    # 索引：未解决告警按触发时间倒序（看板显示）
    bind.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_soc_graph_perf_alerts_unresolved "
        "ON soc_graph_perf_alerts (resolved, triggered_at DESC)"
    ))
    # 索引：按 query_type + severity 分桶
    bind.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_soc_graph_perf_alerts_query "
        "ON soc_graph_perf_alerts (query_type, severity, triggered_at DESC)"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DROP INDEX IF EXISTS idx_soc_graph_perf_alerts_query"))
    bind.execute(sa.text("DROP INDEX IF EXISTS idx_soc_graph_perf_alerts_unresolved"))
    bind.execute(sa.text("DROP TABLE IF EXISTS soc_graph_perf_alerts"))
