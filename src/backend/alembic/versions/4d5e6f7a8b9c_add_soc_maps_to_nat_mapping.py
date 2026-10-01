"""add soc_maps_to table (NAT port-mapping, S2 暴露面归位)

背景（2026-XX-XX）
==================
TL-R479GP-AC 路由器的「虚拟服务器」（DNAT 端口映射）端点实测可拉取：
  POST /stok=<stok>/ds
  body: {"method":"get", "firewall": {"table":"redirect"}}
返回 {"firewall": {"redirect": [...], "count": {...}}, "error_code": 0}
本次共 20 条规则（实测 2026-XX）。

设计依据
========
docs/design/2026-09-30-资产管理AI能力建设方案.md §5.2（S2 暴露面归位数据流）
docs/design/2026-09-30-资产管理AI能力建设方案.md §7.1（AOG-6 复用 TP-Link 扩展）
configs/asset_ontology_v1.yaml（ExposureSurface + maps_to 定义）

新表 soc_maps_to：
  - 字段：source / wan_if / wan_port / wan_ip / protocol / internal_ip / internal_port
    / rule_name / enabled / 时间戳
  - 唯一约束 (source, wan_if, wan_port, protocol, internal_ip, internal_port)
    — 一台路由器上同一外网端口+协议→同一内网目标唯一一条规则
  - 索引：高频查询路径
      - (internal_ip)：S2 暴露面归位 → 反查「内网 IP 有哪些端口对外暴露」
      - (wan_ip)：H2 暴露面分析 API 反查公网入口
  - 不 FK soc_assets（防 collector 写先于资产同步、删资产时误删 NAT）

采集器侧（src/collectors/tplink/）：
  - DataType.NAT_MAPPING 新增（框架枚举）
  - client.get_nat_rules() 拉取 + 标准化
  - collector.collect(DataType.NAT_MAPPING) 一轮一支
  - __main__._collect_and_sync 每轮推两次（asset + nat_mapping）

后续步骤（不在本迁移范围）：
  AOG-6 OH-4.2：NatSyncHandler 接收数据 + upsert
  AOG-3 OH-3.4：GraphBuilder 把 maps_to 边入图
  AOG-2 八维画像④暴露维：消费 maps_to

Revision ID: 4d5e6f7a8b9c
Revises: 8a3f9b2c1d4e
Create Date: 2026-XX-XX
"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, UUID

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "4d5e6f7a8b9c"
down_revision: Union[str, Sequence[str], None] = "8a3f9b2c1d4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建 soc_maps_to 表 + 高频查询索引。"""
    op.create_table(
        "soc_maps_to",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        # 来源标识（路由器 / 采集器），当前固定 'tplink-router'
        sa.Column("source", sa.String(64), nullable=False),
        # 接口名（路由器侧 WAN / LAN1 等标识；当前固定 'WAN'）
        sa.Column("wan_if", sa.String(32), nullable=False, server_default="WAN"),
        # 协议（tcp / udp / all）
        sa.Column("protocol", sa.String(20), nullable=False, server_default="all"),
        # 外网端口
        sa.Column("wan_port", sa.Integer, nullable=False),
        # 外网入口 IP（INET 支持 IPv4/IPv6；nullable 留给 H2 补齐）
        sa.Column("wan_ip", INET, nullable=True),
        # 内网目标 IP
        sa.Column("internal_ip", INET, nullable=False),
        # 内网目标端口
        sa.Column("internal_port", sa.Integer, nullable=False),
        # 规则备注名（路由器侧人类可读名，如 "dify" / "wazuh-web"）
        sa.Column("rule_name", sa.String(128), nullable=True),
        # 是否启用
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        # 时间戳
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"),
                  server_onupdate=sa.text("now()")),
        sa.UniqueConstraint(
            "source", "wan_if", "wan_port", "protocol",
            "internal_ip", "internal_port",
            name="uq_nat_route_source",
        ),
    )

    # 反查索引（按频率从高到低）：
    # 1) internal_ip：S2 暴露面归位 — 「这台机的哪些端口对外暴露」最常见查询路径
    # 2) wan_ip：H2 暴露面分析 API 反查公网入口
    # 3) source：多采集器并存（如未来 NAS/防火墙）的过滤隔离
    # 用 IF NOT EXISTS（PG 9.5+）保证幂等：开发库手工 stamp + 生产库全新跑都安全
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_soc_maps_to_internal_ip "
        "ON soc_maps_to (internal_ip)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_soc_maps_to_wan_ip "
        "ON soc_maps_to (wan_ip)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_soc_maps_to_source "
        "ON soc_maps_to (source)"
    )


def downgrade() -> None:
    """回退：删除索引 + 表。注意：若已落数据则需先备份。"""
    op.execute("DROP INDEX IF EXISTS idx_soc_maps_to_source")
    op.execute("DROP INDEX IF EXISTS idx_soc_maps_to_wan_ip")
    op.execute("DROP INDEX IF EXISTS idx_soc_maps_to_internal_ip")
    op.drop_table("soc_maps_to")