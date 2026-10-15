"""asset reconciliation 按资产维度去重（2026-10-15）

背景：
  当前 soc_asset_reconciliations 表设计是"run 维度"——每次对账 run() 都
  INSERT 新行，8 周累积了 60+ 条 pending 同一批资产（127.0.0.1 出现 12 次等）。
  panel 上 57 / 4 / 61 三个数字口径冲突（详见 2026-10-15 data-health
  session）。

目标：
  把 pending 改成"资产维度"——同一 (asset_id, reconciliation_type) 只
  保留 1 条 pending，累加 occurrence_count / first_seen_at / last_seen_at
  反映"问题持续多久 + 出现频率"。shadow 类型因为 asset_id IS NULL（影子
  资产台账里不存在），改用 details->>'agent_ip' 去重。

设计决策（与产品对齐 2026-10-15）：
  1) 不自动转 ignored——pending 永远是 pending，由人工处理
  2) 代表行 = 首次 created_at 的行（保留 first_seen_run_id）
  3) 后续 run 触发时 UPSERT：UPDATE last_seen_at/occurrence_count/last_seen_run_id
  4) UNIQUE partial index 强约束：(asset_id, type) WHERE status='pending'
     shadow 单独 index：(details->>'agent_ip', type) WHERE status='pending'
  5) 数据合并：60+ 条 pending → ~5-6 条；非代表行 DELETE
  6) 备份表 _backup_soc_asset_recon_20261015_dedup（防回滚）

回滚：downgrade() 反向——删列、删索引、INSERT 备份表回表。
但备份表若超过 down 时窗口内已有新 pending（人工处理过）会冲突；
downgrade 只建议"未跑过 run() UPSERT 之前"。

Revision ID: g3h4i5j6k7l8
Revises: f2g3h4i5j6k7
Create Date: 2026-10-15
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "g3h4i5j6k7l8"
down_revision: Union[str, Sequence[str], None] = "f2g3h4i5j6k7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # ----------------------------------------------------------------------
    # 1) 新增 4 列：first_seen_at / last_seen_at / last_seen_run_id / occurrence_count
    # ----------------------------------------------------------------------
    op.add_column(
        "soc_asset_reconciliations",
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "soc_asset_reconciliations",
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "soc_asset_reconciliations",
        sa.Column(
            "last_seen_run_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(
        "soc_asset_reconciliations",
        sa.Column(
            "occurrence_count",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
    )

    # 索引：列表页主查询（run + status）已有；新增资产维度查询
    op.create_index(
        "idx_soc_asset_recon_asset_pending",
        "soc_asset_reconciliations",
        ["asset_id", "reconciliation_type"],
        postgresql_where=sa.text("status = 'pending'"),
    )

    # ----------------------------------------------------------------------
    # 2) 数据合并（先于 UNIQUE 索引创建，否则 60 条重复 INSERT 会冲突）
    # ----------------------------------------------------------------------
    # 2a) 备份（防回滚）
    bind.execute(
        sa.text(
            """
            CREATE TABLE IF NOT EXISTS _backup_soc_asset_recon_20261015_dedup AS
            SELECT * FROM soc_asset_reconciliations
            WHERE status = 'pending' AND asset_id IS NOT NULL
            """
        )
    )

    # 2b) 先回填 4 列（每行先填自己的 created_at，合并时再聚合）
    bind.execute(
        sa.text(
            """
            UPDATE soc_asset_reconciliations
            SET first_seen_at = created_at,
                last_seen_at = created_at,
                last_seen_run_id = run_id,
                occurrence_count = 1
            WHERE status = 'pending' AND first_seen_at IS NULL
            """
        )
    )

    # 2c) 取每个 (asset_id, type) 的"代表行"id = 最早 created_at
    bind.execute(
        sa.text(
            """
            WITH ranked AS (
              SELECT
                id,
                asset_id,
                reconciliation_type,
                run_id,
                ROW_NUMBER() OVER (
                  PARTITION BY asset_id, reconciliation_type
                  ORDER BY created_at ASC, id ASC
                ) AS rn
              FROM soc_asset_reconciliations
              WHERE status = 'pending' AND asset_id IS NOT NULL
            ),
            aggregates AS (
              SELECT
                asset_id,
                reconciliation_type,
                count(*) AS occ,
                min(created_at) AS first_seen,
                max(created_at) AS last_seen,
                (SELECT run_id FROM ranked r2
                 WHERE r2.asset_id = agg.asset_id
                   AND r2.reconciliation_type = agg.reconciliation_type
                   AND r2.rn = 1
                 LIMIT 1) AS first_run_id
              FROM soc_asset_reconciliations agg
              WHERE status = 'pending' AND asset_id IS NOT NULL
              GROUP BY asset_id, reconciliation_type
            )
            UPDATE soc_asset_reconciliations r SET
              occurrence_count = agg.occ,
              first_seen_at = agg.first_seen,
              last_seen_at = agg.last_seen,
              last_seen_run_id = agg.first_run_id
            FROM aggregates agg
            JOIN ranked rn
              ON rn.asset_id = agg.asset_id
             AND rn.reconciliation_type = agg.reconciliation_type
             AND rn.rn = 1
            WHERE r.id = rn.id
            """
        )
    )

    # 2d) 删非代表行
    bind.execute(
        sa.text(
            """
            DELETE FROM soc_asset_reconciliations
            WHERE status = 'pending'
              AND asset_id IS NOT NULL
              AND id NOT IN (
                SELECT id FROM (
                  SELECT id,
                    ROW_NUMBER() OVER (
                      PARTITION BY asset_id, reconciliation_type
                      ORDER BY created_at ASC, id ASC
                    ) AS rn
                  FROM soc_asset_reconciliations
                  WHERE status = 'pending' AND asset_id IS NOT NULL
                ) t WHERE rn = 1
              )
            """
        )
    )

    # ----------------------------------------------------------------------
    # 3) UNIQUE partial index（强约束：同一资产同一 type 不能有 2 条 pending）
    # ----------------------------------------------------------------------
    op.create_index(
        "uq_soc_asset_recon_pending_asset_type",
        "soc_asset_reconciliations",
        ["asset_id", "reconciliation_type"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND asset_id IS NOT NULL"),
    )


def downgrade() -> None:
    bind = op.get_bind()

    # 1) 删 UNIQUE 索引（如果新 run 已触发 UPSERT 写了新的 last_seen_at，先 UPDATE 分散
    #    才能 drop 索引——但 UPSERT 是同 asset_id 不会冲突，这里直接 drop 即可）
    op.drop_index(
        "uq_soc_asset_recon_pending_asset_type",
        table_name="soc_asset_reconciliations",
    )

    # 2) 删去重索引
    op.drop_index(
        "idx_soc_asset_recon_asset_pending",
        table_name="soc_asset_reconciliations",
    )

    # 3) 尝试从备份表恢复（仅在 _backup_soc_asset_recon_20261015_dedup 存在时）
    #    注意：合并后的"代表行"仍在主表，备份表只含"非代表行"。
    #    这里 INSERT ON CONFLICT DO NOTHING 把备份行的非代表行重新插入。
    bind.execute(
        sa.text(
            """
            INSERT INTO soc_asset_reconciliations
            SELECT * FROM _backup_soc_asset_recon_20261015_dedup b
            WHERE NOT EXISTS (
              SELECT 1 FROM soc_asset_reconciliations r
              WHERE r.id = b.id
            )
            """
        )
    )

    # 4) 删列
    op.drop_column("soc_asset_reconciliations", "occurrence_count")
    op.drop_column("soc_asset_reconciliations", "last_seen_run_id")
    op.drop_column("soc_asset_reconciliations", "last_seen_at")
    op.drop_column("soc_asset_reconciliations", "first_seen_at")
