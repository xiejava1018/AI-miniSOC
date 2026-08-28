"""scanner 通道预期间隔修正 + 清理已停用源的残留行

Revision ID: w2x3y4z5a6b7
Revises: v1w2x3y4z5a6
Create Date: 2026-08-28

背景（生产实测 2026-08-28）：
1. scanner:ports / scanner:discovery 的 expected_interval_seconds=300 是错的——
   300s 是采集器【心跳】频率，不是【数据推送】频率。数据推送只在扫描任务
   完成时发生，central_scan_scheduler 每天 03:00/04:00 建任务 → 实际节奏≈每天一次。
   按 300s 判定导致 scanner:ports 一天里 23+ 小时假 degraded
   （生产页面长期显示"2 个数据源过期未更新"的主因之一）。
   → 回填为 90000s（24h 调度 + 1h 缓冲）。

2. loki:browsing_detection 在生产被 BROWSING_DETECT_ENABLED=false 停用，
   但停用前的 source_health 行残留（interval=300），导致永远显示"过期"。
   → 删除超过 7 天无成功记录的该行。若日后重新启用检测器，
   首次成功会自动重建该行（record_success 无行则 INSERT），无数据损失。

⚠️ 幂等：回填仅当当前值=300（旧值）；删除仅当确实 >7 天无成功。
"""
from typing import Sequence, Union

from alembic import op

revision: str = "w2x3y4z5a6b7"
down_revision: Union[str, Sequence[str], None] = "v1w2x3y4z5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) scanner 两通道：300 → 90000（仅当仍是旧值 300，幂等）
    op.execute(
        "UPDATE soc_source_health SET expected_interval_seconds = 90000 "
        "WHERE source_key IN ('scanner:ports', 'scanner:discovery') "
        "AND expected_interval_seconds = 300"
    )
    # 2) 清理停用源残留行：>7 天无成功记录的 loki:browsing_detection
    op.execute(
        "DELETE FROM soc_source_health "
        "WHERE source_key = 'loki:browsing_detection' "
        "AND last_success_at < now() - interval '7 days'"
    )


def downgrade() -> None:
    # 回滚：恢复 300（仅当当前值=90000）；被删的 browsing 行无法恢复（首次成功会重建）
    op.execute(
        "UPDATE soc_source_health SET expected_interval_seconds = 300 "
        "WHERE source_key IN ('scanner:ports', 'scanner:discovery') "
        "AND expected_interval_seconds = 90000"
    )
