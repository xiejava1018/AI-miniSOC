"""
NAT 端口映射（soc_maps_to）模型

S2 暴露面归位（AOG-6 / OH-6.1 / OH-4.2）：
  - TL-R479GP-AC 的"虚拟服务器"配置（firewall.redirect）由 tplink-collector
    5min 推送，data_type=nat_mapping；
  - 一行 = 一条外网端口 → 内网 IP:端口 的 DNAT 规则；
  - 同时支持 GraphBuilder 建立 `maps_to` 关系（外网 IP → 内网资产），
    喂养 S7 暴露路径推理 / S11 变更风险预测 / 八维画像④暴露维。

本体侧（configs/asset_ontology_v1.yaml）：
  - 类：ExposureSurface（暴露面：公网 IP/端口/域名 + maps_to 内外网映射）
  - 关系：maps_to（domain: exposure-surface）
  - 属性：maps_to_internal_ip 等

设计依据：
  - docs/design/2026-09-30-资产管理AI能力建设方案.md §5.2（S2 暴露面归位数据流）
  - docs/design/2026-09-30-资产管理AI能力建设方案.md §7.1（AOG-6 复用 TP-Link 扩展）
  - configs/asset_ontology_v1.yaml（ExposureSurface + maps_to 定义）

采集器侧端点实测：
  POST /stok=<stok>/ds
  body: {"method": "get", "firewall": {"table": "redirect"}}
  返回: {"firewall": {"redirect": [{"redirect_<ts>": {...}}], "count": {...}}, "error_code": 0}
"""

from sqlalchemy import (
    Column, String, Integer, ForeignKey, DateTime, Boolean, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, INET
from sqlalchemy.sql import func

from app.models.base import Base


class NatMapping(Base):
    """NAT 端口映射（DNAT 虚拟服务器规则）表"""
    __tablename__ = "soc_maps_to"
    __table_args__ = (
        # 一台路由器 + 同一外网端口 + 同一协议 + 同一内网目标 → 一条规则
        # 用 IF + 索引覆盖（UniqueConstraint 自动建索引）
        UniqueConstraint(
            'source', 'wan_ip', 'wan_port', 'protocol',
            'internal_ip', 'internal_port',
            name='uq_nat_route_source',
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())

    # 来源标识（路由器 / 采集器）
    # 当前固定 'tplink-router'；未来 NAS/防火墙可扩展为 'nas-router' 等
    source = Column(String(64), nullable=False)

    # 外网入口（路由器 WAN IP）。INET 类型支持 IPv4/IPv6。
    # 当前 TP-Link collector 未单独从路由器拿公网 IP（NAT 规则本身已含
    # src_dport/dest_ip/dest_port），wan_ip 字段暂 nullable，给 S2
    # 暴露面查询反查时（OH-4.2）补齐。
    wan_ip = Column(INET, nullable=True)

    # 接口名（路由器侧 WAN / LAN1 等标识；当前固定 'WAN'）
    wan_if = Column(String(32), nullable=False, default='WAN')

    # 协议（tcp / udp / all）
    protocol = Column(String(20), nullable=False, default='all')

    # 外网端口
    wan_port = Column(Integer, nullable=False)

    # 内网目标 IP
    internal_ip = Column(INET, nullable=False)

    # 内网目标端口
    internal_port = Column(Integer, nullable=False)

    # 规则备注名（路由器侧配的人类可读名，如 "dify" / "wazuh-web"）
    rule_name = Column(String(128), nullable=True)

    # 是否启用
    enabled = Column(Boolean, nullable=False, default=True)

    # 时间戳（采集时间）
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self):
        return (
            f"<NatMapping(source={self.source}, "
            f"{self.wan_if}:{self.wan_port}/{self.protocol} "
            f"-> {self.internal_ip}:{self.internal_port}, "
            f"enabled={self.enabled})>"
        )