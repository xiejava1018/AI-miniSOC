"""create soc_mcp_keys + mcp config seeds (PR1 用户中心重构 + MCP Key 管理)

Revision ID: d9e0f1a2b3c4
Revises: c3d4e5f6a7b8
Create Date: 2026-10-12 12:00:00.000000

设计文档：docs/design/2026-10-12-用户中心重构与MCP-Key管理设计.md §3

- soc_mcp_keys：用户自助 MCP 接入凭证（只存 SHA-256，明文不落库）
- soc_system_config 种子 category='mcp' 7 项（幂等：已存在则跳过）
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9e0f1a2b3c4'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (key, value, value_type, description)  —— key 为去掉 "mcp." 前缀的短键
_MCP_CONFIG_SEEDS = [
    ("auth.required", "false", "boolean", "MCP 传输层是否强制要求 Bearer Key（生产置 true，本地 dev 免打扰）"),
    ("key.max_per_user", "5", "number", "每用户 active MCP Key 上限"),
    ("key.max_validity_days", "365", "number", "MCP Key 有效期上限（天）"),
    ("key.min_validity_days", "1", "number", "MCP Key 有效期下限（天）"),
    ("key.cache_ttl_seconds", "60", "number", "MCP Key 校验缓存 TTL（秒），注销/禁用主动失效，TTL 兜底"),
    ("key.failure_lock_threshold", "10", "number", "MCP Key 校验连续失败锁定阈值（按 IP）"),
    ("key.failure_lock_minutes", "15", "number", "MCP Key 校验失败锁定时长（分钟）"),
]


def upgrade() -> None:
    """建表 + 索引 + 配置种子（全部幂等）。"""
    op.execute("""
        CREATE TABLE IF NOT EXISTS soc_mcp_keys (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL REFERENCES soc_users(id) ON DELETE CASCADE,
            name VARCHAR(50) NOT NULL,
            key_prefix VARCHAR(16) NOT NULL,
            key_hash VARCHAR(255) NOT NULL UNIQUE,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            expires_at TIMESTAMPTZ NOT NULL,
            last_used_at TIMESTAMPTZ,
            revoked_at TIMESTAMPTZ,
            revoke_reason VARCHAR(100),
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_soc_mcp_keys_user ON soc_mcp_keys (user_id)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_soc_mcp_keys_hash ON soc_mcp_keys (key_hash)
    """)

    # 配置种子：NOT EXISTS 守卫幂等（第二次 upgrade 跑 no-op）
    bind = op.get_bind()
    for key, value, value_type, desc in _MCP_CONFIG_SEEDS:
        bind.execute(
            sa.text(
                """
                INSERT INTO soc_system_config (category, key, value, value_type, is_encrypted, description, created_at, updated_at)
                SELECT 'mcp', :k, :v, :vt, FALSE, :d, now(), now()
                WHERE NOT EXISTS (
                    SELECT 1 FROM soc_system_config WHERE category = 'mcp' AND key = :k
                )
                """,
            ),
            {"k": key, "v": value, "vt": value_type, "d": desc},
        )


def downgrade() -> None:
    """drop 表 + 清 mcp 分类配置种子。"""
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM soc_system_config WHERE category = 'mcp'"))
    op.execute("DROP TABLE IF EXISTS soc_mcp_keys")
