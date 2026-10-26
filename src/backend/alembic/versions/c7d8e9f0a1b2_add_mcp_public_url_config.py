"""mcp_public_url — 配置中心新增「MCP 公共接入地址」

背景（2026-10-26 Cloudflare Tunnel / MCP 公网接入排查）：

个人中心「MCP 接入」页生成客户端配置时，把 URL 硬编码成
`http://{当前访问主机}:8100/mcp`。这个写法有三个问题：

1. **带 8100 端口** —— 8100 是 MCP 独立进程在**内网**的监听端口，公网并不通。
   公网入口是 Cloudflare Tunnel → 102:8080 (nginx) → 反代到 127.0.0.1:8100。
   用户把带 8100 的地址粘进 workbuddy 一定连不上（表现为"连接超时"）。
2. **强制 http** —— 公网入口是 https（CF 终止 TLS）。
3. **依赖 window.location.hostname** —— 运维改了域名/反代后，页面给的地址
   仍按当前访问主机推导，容易与真实对外地址不一致。

因此把「对外的 MCP 接入地址」提到配置中心，由运维显式配置；
留空时前端按当前访问 origin 兜底推导（至少不会再带 8100 端口）。

数据落点：soc_system_config，category='general'，key='mcp_public_url'。
之所以放 'general' 而不是新建分类：
  - /api/v1/public/system-info 按 category='general' + key 白名单取值，
    新增一个 key 即可被前端读到，无需改接口形状；
  - 'general' 分类在「高级配置」页（/system/config）按 category 直接读写
    soc_system_config，不依赖 soc_config_schema 注册行（见 j5k6l7m8n9o0 的说明），
    所以运维不装 schema 行也能在页面上编辑这一项。

幂等：soc_system_config 上没有 (category, key) 唯一约束（见 u0a1b2c3d4e5 注释），
沿用 WHERE NOT EXISTS 写法，已存在则跳过、不覆盖运维已改的值。

Revision ID: c7d8e9f0a1b2
Revises: b2c3d4e5f6a7
Create Date: 2026-10-26
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 默认留空：前端按当前访问 origin 兜底推导（不带 8100 端口）。
    # 运维可在「高级配置 → general → mcp_public_url」填入反代后的对外地址，
    # 例如 https://aisoc.example.com/mcp
    op.execute(
        """
        INSERT INTO soc_system_config (category, key, value, value_type, description)
        SELECT 'general', 'mcp_public_url', '', 'string',
               'MCP 客户端接入地址（含协议与路径）；留空则按当前访问地址自动推导'
        WHERE NOT EXISTS (
            SELECT 1 FROM soc_system_config
            WHERE category = 'general' AND key = 'mcp_public_url'
        )
        """
    )


def downgrade() -> None:
    # 只删本迁移自己种的这一个 key，不动运维后来改过的其它 general 配置
    op.execute(
        """
        DELETE FROM soc_system_config
        WHERE category = 'general' AND key = 'mcp_public_url'
        """
    )
