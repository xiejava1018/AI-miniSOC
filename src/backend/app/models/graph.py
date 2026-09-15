"""
资产知识图谱模型（v1）

新增表：
  - soc_graph_nodes     图节点（异构实体统一寻址）
  - soc_graph_edges     图边（邻接表 + 生命周期 + 置信度 + 证据）
  - soc_network_links   网络链路（v1 仅人工登记，采集留 v2）
  - soc_account_person  账号字符串 → 自然人 user_id 映射

详见 docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6.2④⑤⑥⑦
"""
from __future__ import annotations

from sqlalchemy import (
    BigInteger, CheckConstraint, Column, DateTime, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint, text as sa_text,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.models.base import Base


class GraphNode(Base):
    """图节点：跨实体统一寻址（asset / port / vuln / ip / person / system ...）

    node_key 格式：``<type>:<identifier>``
      - asset:           asset:<uuid>
      - port:            port:<ip>:<port>/<proto>
      - vulnerability:   vuln:<uuid>
      - account:         account:<name>
      - ip:              ip:<addr>            （未纳管 IP 或外部 IP）
      - business_system: system:<code>
      - person:          person:<user_id>      （user_id 为 Integer，转 str）
      - network_segment: segment:<name>
      - alert_group:     alertgroup:<uuid>

    字段说明：
      - ref_table / ref_id：实体来源（便于溯源），可空
      - props：渲染用属性快照（避免前端渲染时 join 全表）
      - props_synced_at：快照同步时间，用于失效检测
    """
    __tablename__ = "soc_graph_nodes"
    __table_args__ = (
        CheckConstraint("node_type IN ("
                        "'asset','port','vulnerability','account','ip',"
                        "'business_system','person','segment','alert_group'"
                        ")", name="ck_graph_node_type"),
    )

    node_key = Column(Text, primary_key=True)
    node_type = Column(String(30), nullable=False, index=True)
    ref_table = Column(String(64))
    ref_id = Column(Text)
    label = Column(Text, nullable=False)
    # 注：必须用 sa.text("'{}'::jsonb") 而非 func.text("...")。
    #   func.text 会让 SQLAlchemy 编译成 DEFAULT text('{}'::jsonb)，
    #   外层 text() 函数包裹后 PG 不再识别为 JSONB cast，导致建表失败。
    #   sa.text 输出裸表达式 DEFAULT '{}'::jsonb，PG 直接接受。
    props = Column(JSONB, nullable=False, server_default=sa_text("'{}'::jsonb"))
    props_synced_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> dict:
        return {
            "node_key": self.node_key,
            "node_type": self.node_type,
            "ref_table": self.ref_table,
            "ref_id": self.ref_id,
            "label": self.label,
            "props": self.props or {},
            "props_synced_at": self.props_synced_at.isoformat() if self.props_synced_at else None,
        }


class GraphEdge(Base):
    """图边：邻接表 + 生命周期 + 置信度 + 证据

    字段说明（参考 ``soc_asset_sources`` 多源范式 + Cartography 生命周期设计）：
      - direction:      directed | undirected
      - weight:         路径代价（越小越易走）
      - confidence:     0.0~1.0，边置信度（D1=1.0 / D2=0.7-0.9 / D3=0.3-0.5）
      - sources:        JSONB，多源融合（如 ["wazuh","manual","inferred"]）
      - last_seen_by_source: JSONB，每来源最后观测时间
      - evidence:       JSONB，证据回指（如 {table:"soc_identity_events", count:202, sample_ids:[...]}）
      - first_seen / last_seen / expires_at: 生命周期，观测类边按窗口淘汰
    """
    __tablename__ = "soc_graph_edges"
    __table_args__ = (
        UniqueConstraint("src_key", "dst_key", "rel_type", name="uq_graph_edge"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_edge_conf"),
        CheckConstraint("direction IN ('directed', 'undirected')", name="ck_edge_dir"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    src_key = Column(Text,
                     ForeignKey("soc_graph_nodes.node_key", ondelete="CASCADE"),
                     nullable=False, index=True)
    dst_key = Column(Text,
                     ForeignKey("soc_graph_nodes.node_key", ondelete="CASCADE"),
                     nullable=False, index=True)
    rel_type = Column(String(64), nullable=False, index=True)
    direction = Column(String(16), nullable=False, default="directed")
    weight = Column(Numeric(5, 3), nullable=False, default=1.0)
    confidence = Column(Numeric(4, 3), nullable=False, default=1.0)
    sources = Column(JSONB, nullable=False, server_default=sa_text("'[]'::jsonb"))
    last_seen_by_source = Column(JSONB, nullable=False,
                                 server_default=sa_text("'{}'::jsonb"))
    evidence = Column(JSONB, nullable=False, server_default=sa_text("'{}'::jsonb"))
    first_seen = Column(DateTime(timezone=True))
    last_seen = Column(DateTime(timezone=True), index=True)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now(), onupdate=func.now())

    def to_dict(self) -> dict:
        """API/序列化用。sources/evidence/last_seen_by_source 已是 dict/list。"""
        return {
            "id": str(self.id),
            "src_key": self.src_key,
            "dst_key": self.dst_key,
            "rel_type": self.rel_type,
            "direction": self.direction,
            "weight": float(self.weight) if self.weight is not None else 1.0,
            "confidence": float(self.confidence) if self.confidence is not None else 1.0,
            "sources": self.sources or [],
            "last_seen_by_source": self.last_seen_by_source or {},
            "evidence": self.evidence or {},
            "first_seen": self.first_seen.isoformat() if self.first_seen else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class NetworkLink(Base):
    """网络链路（v1 仅人工登记，采集留 v2）

    字段说明：
      - src_key / dst_key：节点 key（不强制 FK 到 soc_graph_nodes，允许节点尚未建边）
      - link_type: l2|l3|vpn|route
      - source:   manual | nmap | ...
    """
    __tablename__ = "soc_network_links"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    src_key = Column(Text, nullable=False)
    dst_key = Column(Text, nullable=False)
    link_type = Column(String(16), nullable=False, default="l2")
    confidence = Column(Numeric(4, 3), nullable=False, default=0.5)
    source = Column(String(32), nullable=False, default="manual")
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AccountPerson(Base):
    """账号字符串 → 自然人 user_id 映射（IdentityGraphBuilder 据此产生 owned_by 边）

    字段说明：
      - account:      主键，账号字符串（来自 soc_identity_bindings.account）
      - user_id:      soc_users.id（Integer，非 UUID）
      - match_method: manual | email | phone | rule
      - confidence:   0.0~1.0，匹配置信度
      - verified_at:  人工校验时间
    """
    __tablename__ = "soc_account_person"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_account_person_conf"),
    )

    account = Column(Text, primary_key=True)
    user_id = Column(Integer, ForeignKey("soc_users.id", ondelete="SET NULL"), nullable=True)
    match_method = Column(String(20), nullable=False, default="manual")
    confidence = Column(Numeric(4, 3), nullable=False, default=1.0)
    verified_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now(), onupdate=func.now())

    # 关系
    user = relationship("User", foreign_keys=[user_id])