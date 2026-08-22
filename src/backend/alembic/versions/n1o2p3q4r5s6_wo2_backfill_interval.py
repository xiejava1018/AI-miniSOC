"""P4 WO-2 补丁：回填 source_health.expected_interval_seconds (P3/ops-reorg 续 4)

Revision ID: n1o2p3q4r5s6
Revises: m1n2o3p4q5r6
Create Date: 2026-08-22

背景（验收报告 §2 WO-2）：
- /data-health 页面的 _source_status() 守卫 `if interval and sh.last_success_at:`
  跳过 degraded 判定——若 expected_interval_seconds=NULL 即使 last_success_at
  过期数天也不标红
- 当前生产：tplink:collector / wazuh:agents 行的 expected_interval_seconds=NULL
- 来源：原 AssetSyncHandler.handle:83 record_success() 没传 expected_interval_seconds
- 本次只做数据回填（让 degraded 判定对现有行也生效）；
  业务侧 record_success 传 interval 在代码改动里同步进行

参考间隔：
  tplink:collector  300s (5min) — src/collectors/tplink/run_collector.py:47
  wazuh:agents      300s (5min) — 与 tplink 同步推送（生产实测两边 success 计数一致）

幂等：WHERE expected_interval_seconds IS NULL，只回填未设置过的行。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "n1o2p3q4r5s6"
down_revision: Union[str, Sequence[str], None] = "m1n2o3p4q5r6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            UPDATE soc_source_health
            SET expected_interval_seconds = 300,
                updated_at = NOW()
            WHERE source_key IN ('tplink:collector', 'wazuh:agents')
              AND expected_interval_seconds IS NULL
            """
        )
    )


def downgrade() -> None:
    # 回退到 NULL（与 v1.2 验收时的状态一致）
    op.execute(
        sa.text(
            """
            UPDATE soc_source_health
            SET expected_interval_seconds = NULL,
                updated_at = NOW()
            WHERE source_key IN ('tplink:collector', 'wazuh:agents')
              AND expected_interval_seconds = 300
            """
        )
    )