"""arl 分类 — 配置中心新增 ARL-Next 集成配置（OH-ARL.7）

背景（docs/design/2026-11-14-ARL-Next集成设计方案.md §6.5 M1/OH-ARL.7）：

ARL-Next 集成一期（OH-ARL.1~5）落地后，连接配置需要可运维化。
本迁移在配置中心新增 'arl' 分类，**只存非敏感项**：
  - arl.base_url       ARL 网关地址（Nginx 5173 反代 /api）
  - arl.scope_ids      授权范围白名单（C1，逗号分隔 scope_id）
  - arl.sync_interval_s 采集间隔（默认 1800s，与 collector 默认一致）
  - arl.enabled        是否启用采集（采集器部署编排读取）

凭据（ARL_API_KEY / ARL_PASSWORD）**不入配置中心**：system_configs API
未接 encryption_service（is_encrypted 字段无实现），入库即明文——违反
C4「凭据不落库明文」。凭据由部署 env 注入（src/collectors/.env 的
ARL_API_KEY / ARL_USERNAME / ARL_PASSWORD，compose environment 透传），
加密存储列为二期（依赖配置中心加密链路，独立任务）。

幂等：soc_system_config 无 (category, key) 唯一约束，沿用
WHERE NOT EXISTS 写法（已存在则跳过、不覆盖运维已改的值）。

Revision ID: arlx1y2z3w4v5
Revises: n2o3p4q5r6s7
Create Date: 2026-11-15
"""

from typing import Sequence, Union

from alembic import op

revision: str = "arlx1y2z3w4v5"
down_revision: Union[str, Sequence[str], None] = "n2o3p4q5r6s7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROWS = [
    # (key, value, description)
    ("arl.base_url", "", "ARL-Next 网关地址（如 https://192.168.0.42:5173）"),
    ("arl.scope_ids", "", "授权范围白名单（逗号分隔 scope_id；留空=全部资产组）"),
    ("arl.sync_interval_s", "1800", "采集间隔秒数（默认 1800，与 arl-collector 一致）"),
    ("arl.enabled", "true", "是否启用 ARL 采集（采集器部署编排读取）"),
]


def upgrade() -> None:
    for key, value, desc in _ROWS:
        op.execute(
            f"""
            INSERT INTO soc_system_config (category, key, value, value_type, description)
            SELECT 'arl', '{key}', '{value}', 'string', '{desc}'
            WHERE NOT EXISTS (
                SELECT 1 FROM soc_system_config
                WHERE category = 'arl' AND key = '{key}'
            )
            """
        )


def downgrade() -> None:
    op.execute(
        "DELETE FROM soc_system_config WHERE category = 'arl' "
        "AND key IN ('arl.base_url', 'arl.scope_ids', 'arl.sync_interval_s', 'arl.enabled')"
    )
