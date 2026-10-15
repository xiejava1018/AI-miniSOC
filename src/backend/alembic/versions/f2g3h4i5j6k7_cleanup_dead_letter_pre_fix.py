"""
清理 soc_sync_dead_letter 修复前的 wazuh_agent_id 漂移死信（PR：数据健康历史噪音）

背景：
  2026-10-08 21:51 提交 1bf5f52 在 asset_sync_handler 引入
  _release_stale_wazuh_agent_id()，解决"partial unique index 触发
  UniqueViolation → 同 session 后续 17 条全部 500"问题。
  修复前的死信（约 46 条）至今仍挂在 soc_sync_dead_letter 表
  (resolved=false)，让数据健康页面持续展示"陈年故障"。

本迁移把修复前（created_at < 2026-10-08 UTC）的 wazuh_agent_id 漂移
ValueError 死信标记 resolved=true，附 replay_count 保留 0 / last_replayed_at
= now() 表示"批量归档时间"（不是真重放过）。

判定条件（必须全部满足才归档）：
  - created_at < 2026-10-08 UTC（修复前）
  - error_class = 'ValueError'
  - error_message LIKE 'wazuh_agent_id%已被活跃资产%占用%'（明确漂移语义）

不影响：
  - 数据库 schema
  - 修复后产生的死信（按业务正常 retry）
  - raw_item（保留审计价值，即使 resolved 也不删）
  - replay_count（保留为 0，表示未真重放）

幂等：WHERE resolved=false 守卫；重复执行 N 次结果相同。

回滚（downgrade）：
  把刚才标记 resolved=true 的行改回 false，附带 audit 记录
  （soc_sync_dead_letter_cleanup_audit 表）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2g3h4i5j6k7"
down_revision: Union[str, None] = "e1f2g3h4i5j6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FIX_DATE_UTC = "2026-10-08 00:00:00+00"


def upgrade() -> None:
    bind = op.get_bind()

    # 0. 备份：将命中的死信 ID 记录到 audit 表（供回滚或审计）
    bind.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS soc_sync_dead_letter_cleanup_audit (
            cleaned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            revision VARCHAR(64) NOT NULL,
            dead_letter_id UUID NOT NULL,
            source VARCHAR(100),
            data_type VARCHAR(50),
            created_at TIMESTAMPTZ,
            error_class VARCHAR(100),
            error_message_preview TEXT,
            PRIMARY KEY (revision, dead_letter_id)
        )
    """))

    bind.execute(sa.text(f"""
        INSERT INTO soc_sync_dead_letter_cleanup_audit (
            revision, dead_letter_id, source, data_type, created_at,
            error_class, error_message_preview
        )
        SELECT
            'f2g3h4i5j6k7' AS revision,
            id, source, data_type, created_at,
            error_class, LEFT(error_message, 200)
        FROM soc_sync_dead_letter
        WHERE created_at < '{FIX_DATE_UTC}'
          AND error_class = 'ValueError'
          AND error_message LIKE 'wazuh_agent_id%已被活跃资产%占用%'
          AND resolved = false
        ON CONFLICT (revision, dead_letter_id) DO NOTHING
    """))

    # 1. 真改：标记 resolved=true，last_replayed_at=now 表示"批量归档时间"
    result = bind.execute(sa.text(f"""
        UPDATE soc_sync_dead_letter
        SET resolved = true,
            last_replayed_at = NOW()
        WHERE created_at < '{FIX_DATE_UTC}'
          AND error_class = 'ValueError'
          AND error_message LIKE 'wazuh_agent_id%已被活跃资产%占用%'
          AND resolved = false
    """))

    print(f"[f2g3h4i5j6k7] dead_letter cleanup: {result.rowcount} rows marked resolved")
    print(f"[f2g3h4i5j6k7] backup stored in soc_sync_dead_letter_cleanup_audit")


def downgrade() -> None:
    bind = op.get_bind()

    # 反向：把刚标记 resolved=true 的恢复为 false
    # 仅恢复本迁移处理的（其他 resolved=true 不动）
    bind.execute(sa.text("""
        UPDATE soc_sync_dead_letter d
        SET resolved = false,
            last_replayed_at = NULL
        FROM soc_sync_dead_letter_cleanup_audit a
        WHERE a.dead_letter_id = d.id
          AND a.revision = 'f2g3h4i5j6k7'
    """))
    bind.execute(sa.text("""
        DELETE FROM soc_sync_dead_letter_cleanup_audit
        WHERE revision = 'f2g3h4i5j6k7'
    """))
    print("[f2g3h4i5j6k7] downgrade: restored resolved=false for cleaned rows")
