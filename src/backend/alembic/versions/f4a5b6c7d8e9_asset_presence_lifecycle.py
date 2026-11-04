"""资产存在性证据层：last_seen/lifecycle + 观测表 + 覆盖凭证表

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-11-04

背景：192.168.0.37 资产停在 10-25 的 online 状态、内网定时扫描连续 18 天
失败无人知晓——"缺席不留痕 + 断言永不过期 + 覆盖无凭证"三个结构性缺口。
本迁移落 P1/P2/P3 的 schema：soc_assets 4 列 + 2 张新表 + 配置中心阈值种子。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, Sequence[str], None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("soc_assets", sa.Column("last_seen_at", sa.DateTime(timezone=True)))
    op.add_column("soc_assets", sa.Column("miss_streak", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("soc_assets", sa.Column("last_scan_missed_at", sa.DateTime(timezone=True)))
    op.add_column("soc_assets", sa.Column("lifecycle_state", sa.String(20), nullable=False, server_default="active"))
    op.create_index("ix_soc_assets_lifecycle_state", "soc_assets", ["lifecycle_state"])

    # 回填：存量资产按最有利的已有时间戳初始化 last_seen_at，避免迁移后立刻全员失联
    op.execute("""
        UPDATE soc_assets
        SET last_seen_at = GREATEST(
            COALESCE(last_synced_at, created_at),
            COALESCE(updated_at, created_at),
            created_at
        )
    """)

    op.create_table(
        "soc_asset_observations",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("asset_id", UUID(as_uuid=True), sa.ForeignKey("soc_assets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("evidence_type", sa.String(20), nullable=False, server_default="sync"),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("obs_count", sa.BigInteger(), nullable=False, server_default="1"),
        sa.UniqueConstraint("asset_id", "source", name="uq_asset_observation_source"),
    )
    op.create_index("ix_soc_asset_observations_asset_id", "soc_asset_observations", ["asset_id"])

    op.create_table(
        "soc_scan_coverage",
        sa.Column("id", sa.BigInteger(), autoincrement=True, primary_key=True),
        sa.Column("task_uuid", UUID(as_uuid=True), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False),
        sa.Column("scope", sa.String(20)),
        sa.Column("target_value", sa.String(100), nullable=False),
        sa.Column("target_type", sa.String(10)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("hosts_found", sa.Integer()),
        sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("settled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("settled_at", sa.DateTime(timezone=True)),
        sa.Column("miss_marked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("task_uuid", "target_value", name="uq_scan_coverage_task_target"),
    )
    op.create_index("ix_soc_scan_coverage_task_uuid", "soc_scan_coverage", ["task_uuid"])

    # 阈值进配置中心（非硬编码；ON CONFLICT 不依赖唯一约束，先查后插，幂等）
    bind = op.get_bind()
    for key, value_type, value, desc in [
        ("miss_streak_threshold", "int", "2", "连续缺席几次成功覆盖的扫描后标记为 unverified（疑似失联）"),
        ("offline_days", "int", "30", "最后一次观测距今超过 N 天则升级为 presumed_offline（疑似下线）"),
        ("fail_alert_threshold", "int", "3", "scheduled 内网扫描连续失败 N 次触发数据健康告警"),
    ]:
        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM soc_system_config WHERE category = :c AND key = :k"
            ),
            {"c": "asset_lifecycle", "k": key},
        ).fetchone()
        if not exists:
            bind.execute(
                sa.text(
                    "INSERT INTO soc_system_config (category, key, value, value_type, description)"
                    " VALUES (:c, :k, :v, :t, :d)"
                ),
                {"c": "asset_lifecycle", "k": key, "v": value, "t": value_type, "d": desc},
            )


def downgrade() -> None:
    op.drop_index("ix_soc_scan_coverage_task_uuid", table_name="soc_scan_coverage")
    op.drop_table("soc_scan_coverage")
    op.drop_index("ix_soc_asset_observations_asset_id", table_name="soc_asset_observations")
    op.drop_table("soc_asset_observations")
    op.drop_index("ix_soc_assets_lifecycle_state", table_name="soc_assets")
    op.drop_column("soc_assets", "lifecycle_state")
    op.drop_column("soc_assets", "last_scan_missed_at")
    op.drop_column("soc_assets", "miss_streak")
    op.drop_column("soc_assets", "last_seen_at")
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM soc_system_config WHERE category = 'asset_lifecycle'")
    )
