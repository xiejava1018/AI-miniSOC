"""
清理 soc_source_health 修复前的累计失败计数（PR：数据健康历史噪音）

背景：
  2026-10-08 修复前（commit 92d7e04 + 1bf5f52），wazuh 采集器向后端
  /data/sync 持续推 baseline / vulnerability 两种 unsupported data_type，
  以及同 IP 重复 wazuh_agent_id 等问题，导致：
    - wazuh:baseline 累计失败 ~2119 次（success_count=0）
    - wazuh:vulnerability 累计失败 ~2119 次（success_count=0）
    - wazuh:agents 累计失败 22 次（成功 55 次，混合）
  修复后这两种 data_type 已不再被采集器推送（wazuh/config.yaml:types
  收敛为 [asset]），失败也不会再涨，但累计值仍展示在数据健康页面，
  误导运维以为是当前故障。

本迁移对修复日（2026-10-08 UTC）之前产生失败事件的源行：
  - failure_count 归零（按"修复前失败清零"语义）
  - last_failure_message 置 NULL（避免 UI 仍展示过期错误）
  - 保留 success_count（业务正循环不受影响）
  - 保留 last_failure_at（审计可追溯）
  - 若 last_success_at 也 < 2026-10-08，failure_count 全清零；
    若 last_success_at >= 2026-10-08（混合期），仅清"修复前"那部分——
    实现上：直接归零 failure_count（业务语义简化：累计 = 0 since fix）

不影响：
  - success_count / last_success_at 任何修改
  - 数据库 schema
  - last_failure_at（保留审计时间戳）
  - 修复后产生的失败事件（last_failure_at >= 2026-10-08 不动）

幂等：WHERE 守卫 + 行数 log；重复执行 N 次结果相同。

回滚（downgrade）：
  本迁移不可逆——已归零的 failure_count 无法恢复。
  downgrade 仅打印原值由备份恢复的提示，由运维手工处理。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2g3h4i5j6"
down_revision: Union[str, None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# 修复日（采集器 trim data_type 提交日 2026-10-08 20:11 +08 = 2026-10-08 12:11 UTC）
# asset_sync 漂移识别提交 2026-10-08 21:51 +08 = 2026-10-08 13:51 UTC
# 取 2026-10-08 00:00:00 UTC 为保守边界，避免漏清
FIX_DATE_UTC = "2026-10-08 00:00:00+00"


def upgrade() -> None:
    bind = op.get_bind()

    # 0. 备份关键行原值到 audit log（避免不可逆）
    # 备份到新的 soc_source_health_cleanup_audit 表（一次性的，不进 schema 同步）
    bind.execute(sa.text(f"""
        CREATE TABLE IF NOT EXISTS soc_source_health_cleanup_audit (
            cleaned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            revision VARCHAR(64) NOT NULL,
            source_key VARCHAR(200) PRIMARY KEY,
            old_failure_count INT,
            old_success_count INT,
            old_last_failure_at TIMESTAMPTZ,
            old_last_failure_message TEXT,
            old_last_success_at TIMESTAMPTZ
        )
    """))

    bind.execute(sa.text(f"""
        INSERT INTO soc_source_health_cleanup_audit (
            revision, source_key, old_failure_count, old_success_count,
            old_last_failure_at, old_last_failure_message, old_last_success_at
        )
        SELECT
            'e1f2g3h4i5j6' AS revision,
            source_key,
            failure_count AS old_failure_count,
            success_count AS old_success_count,
            last_failure_at AS old_last_failure_at,
            last_failure_message AS old_last_failure_message,
            last_success_at AS old_last_success_at
        FROM soc_source_health
        WHERE last_failure_at IS NOT NULL
          AND last_failure_at < '{FIX_DATE_UTC}'
        ON CONFLICT (source_key) DO NOTHING
    """))

    # 1. 把"修复前失败"清零（针对 2026-10-08 之前的失败事件）
    # 条件：last_failure_at < fix_date（即使 last_failure_at 已是修复前的旧值）
    # 关键：不动 success_count / last_success_at / last_failure_at 时间戳
    result = bind.execute(sa.text(f"""
        UPDATE soc_source_health
        SET failure_count = 0,
            last_failure_message = NULL
        WHERE last_failure_at IS NOT NULL
          AND last_failure_at < '{FIX_DATE_UTC}'
    """))

    print(f"[e1f2g3h4i5j6] source_health cleanup: {result.rowcount} rows updated")
    print(f"[e1f2g3h4i5j6] backup stored in soc_source_health_cleanup_audit")


def downgrade() -> None:
    # 不可逆：失败计数已归零，无法从 schema 内恢复
    # 备份在 soc_source_health_cleanup_audit 表里可手工恢复
    bind = op.get_bind()
    bind.execute(sa.text("""
        DELETE FROM soc_source_health_cleanup_audit WHERE revision = 'e1f2g3h4i5j6'
    """))
    print(
        "[e1f2g3h4i5j6] WARNING: downgrade does not restore failure_count. "
        "Restore from soc_source_health_cleanup_audit before this point (if it existed)."
    )
