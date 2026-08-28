"""source_health display_name 中文名 + expected_interval_seconds 回填

Revision ID: v1w2x3y4z5a6
Revises: u3v4w5x6y7z8
Create Date: 2026-08-28

背景：soc_source_health 表的 display_name 列在采集器初次 record_success 时填的是
source_key 字面值（用户感知"全是技术名而非中文"），expected_interval_seconds 也是
部分行缺失导致 _source_status() 跳 degraded 判定。

数据修复（一次性）：
  1. 7 个 source_key 补中文 display_name（页面可读性）
  2. loki:browsing / opensearch:vuln 两条补 expected_interval_seconds
     （WO-2 验收报告 #2 的 backfill 迁移只补了 tplink:collector / wazuh:agents）

⚠️ idempotent：UPDATE 加 WHERE 条件（display_name=source_key OR interval IS NULL），
   已正确填过的行不会被覆盖。
"""
from typing import Sequence, Union

from alembic import op

revision: str = "v1w2x3y4z5a6"
down_revision: Union[str, Sequence[str], None] = "u3v4w5x6y7z8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (source_key, display_name, expected_interval_seconds)
_CHANGES = [
    ("loki:browsing", "路由上网行为日志（Loki）", 300),
    ("loki:browsing_detection", "上网行为异常检测（Loki）", 300),
    ("opensearch:vuln", "OpenSearch 漏洞状态同步", 3600),
    ("scanner:discovery", "攻击面扫描-资产发现", 300),
    ("scanner:ports", "攻击面扫描-端口服务", 300),
    ("tplink:collector", "TP-Link 路由器资产采集", 300),
    ("wazuh:agents", "Wazuh Agent 资产同步", 300),
]


def upgrade() -> None:
    for sk, name, interval in _CHANGES:
        # display_name：仅当当前是 source_key 字面值才覆盖（不破坏人工已填）
        op.execute(
            f"UPDATE soc_source_health "
            f"SET display_name = '{name}' "
            f"WHERE source_key = '{sk}' AND display_name = '{sk}'"
        )
        # expected_interval_seconds：仅 NULL 时回填
        op.execute(
            f"UPDATE soc_source_health "
            f"SET expected_interval_seconds = {interval} "
            f"WHERE source_key = '{sk}' AND expected_interval_seconds IS NULL"
        )


def downgrade() -> None:
    for sk, name, interval in _CHANGES:
        # 回滚：display_name 恢复为 source_key，interval 置 NULL
        op.execute(
            f"UPDATE soc_source_health "
            f"SET display_name = '{sk}' "
            f"WHERE source_key = '{sk}' AND display_name = '{name}'"
        )
        op.execute(
            f"UPDATE soc_source_health "
            f"SET expected_interval_seconds = NULL "
            f"WHERE source_key = '{sk}' AND expected_interval_seconds = {interval}"
        )