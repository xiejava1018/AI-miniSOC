"""
资产知识图谱工具函数

核心职责：
  - 节点归并：同一 IP 不允许产生两种 node_key（消除边分叉歧义）
  - 外网 IP 判定：避免把内网跳板当外网
  - 节点 / 边的幂等 upsert（避免重复插入 + 自动补节点）
  - 过期边清理

设计依据：docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6.3
"""
from __future__ import annotations

import ipaddress
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import GraphEdge, GraphNode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 边类型分档常量（D1 确定性 / D2 观测 / D3 推断 / D4 人工）
# 详见方案 §4.3
# ---------------------------------------------------------------------------
D1_TYPES = {
    "has_port", "has_vuln", "port_has_vuln",
    "belongs_to_system", "owned_by", "system_owned_by", "runs_on",
}
D2_TYPES = {
    "login_to", "login_from", "session_on", "external_access",
}
D3_TYPES = {"same_segment", "shared_tag", "co_alerted"}
D4_TYPES = {"depends_on"}

# D1+D2 = 可进入攻击路径计算
ATTACK_EDGE_TYPES = D1_TYPES | D2_TYPES
# D3 = 仅用于影响面提示，不入攻击路径，UI 强制标灰
INFERRED_TYPES = D3_TYPES

# 边衰减窗口（按 §6.3.2 规则卡）
EDGE_DECAY_DAYS: dict[str, int] = {
    "login_to": 30,
    "login_from": 30,
    "session_on": 90,
    "external_access": 7,
    "alerted_on": 90,        # 簇关闭后 90 天
    "co_alerted": 90,
    "same_segment": 365,     # 拓扑变化少，年度重算
    "shared_tag": 90,
}


# ---------------------------------------------------------------------------
# 节点归并辅助函数（消除边分叉歧义的关键，所有 builder 必须用）
# ---------------------------------------------------------------------------

def resolve_asset_or_ip_node(db: Session, ip: str) -> str:
    """IP 已纳管 → ``asset:<uuid>``；否则 → ``ip:<addr>``

    所有 builder **必须**通过此函数产生 node_key，禁止直接拼 ``ip:<addr>``。
    否则同一 IP 在不同 builder 生成两种节点会产生分叉歧义。

    Args:
        db: SQLAlchemy Session
        ip:  IP 字符串（如 '192.168.0.30'）

    Returns:
        node_key 字符串
    """
    from app.models import Asset
    if not ip:
        # 空 IP 永不应当节点 key；但为安全兜底，返回 ip:_unknown
        return "ip:_unknown"
    asset = db.query(Asset).filter(Asset.asset_ip == ip).first()
    return f"asset:{asset.id}" if asset else f"ip:{ip}"


# ---------------------------------------------------------------------------
# 外网 IP 判定（避免把内网跳板当外网）
# ---------------------------------------------------------------------------

_V4_PRIVATE = [
    ipaddress.ip_network(n) for n in [
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "127.0.0.0/8",
        "169.254.0.0/16", "100.64.0.0/10", "224.0.0.0/4", "0.0.0.0/8",
    ]
]
_V6_PRIVATE = [
    ipaddress.ip_network(n) for n in ["fc00::/7", "fe80::/10", "::1/128"]
]


def is_external_ip(ip_str: str) -> bool:
    """判定 IP 是否为外网 IP（用于 external_access 边过滤）。

    内网 / 链路本地 / 组播 / 回环 / 未指定地址 一律视为非外网。
    非法 IP 字符串（非 IPv4/IPv6）返回 False，宁缺勿滥。
    """
    if not ip_str:
        return False
    try:
        ip_obj = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    nets = _V4_PRIVATE if ip_obj.version == 4 else _V6_PRIVATE
    return not any(ip_obj in net for net in nets)


# ---------------------------------------------------------------------------
# 节点 upsert
# ---------------------------------------------------------------------------


def ensure_node(
    db: Session,
    node_key: str,
    node_type: str,
    label: str,
    *,
    ref_table: Optional[str] = None,
    ref_id: Optional[str] = None,
    props: Optional[dict] = None,
    props_synced_at: Optional[datetime] = None,
) -> None:
    """幂等 upsert 一个节点（不存在则插入，存在则轻量更新 label/props）。

    设计：使用 PostgreSQL ``ON CONFLICT DO UPDATE``，单条 SQL 完成，
    无 SELECT-INSERT 双步操作的竞态。
    """
    values: dict[str, Any] = {
        "node_key": node_key,
        "node_type": node_type,
        "label": label,
        "ref_table": ref_table,
        "ref_id": ref_id,
        "props": props or {},
        "props_synced_at": props_synced_at or datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    stmt = (
        pg_insert(GraphNode)
        .values(**values)
        .on_conflict_do_update(
            index_elements=["node_key"],
            set_={
                "label": values["label"],
                "props": values["props"],
                "props_synced_at": values["props_synced_at"],
                "updated_at": values["updated_at"],
                # 若新 props 不空则覆盖 ref_table/ref_id；否则保留原值
                # （无法直接条件，简化处理：始终覆盖）
                "ref_table": values["ref_table"],
                "ref_id": values["ref_id"],
            },
        )
    )
    db.execute(stmt)


def ensure_nodes_batch(
    db: Session,
    nodes: Iterable[dict],
) -> None:
    """批量 upsert 节点。nodes 中每个 dict 必须含 node_key/node_type/label。"""
    nodes_list = list(nodes)
    if not nodes_list:
        return
    now = datetime.now(timezone.utc)
    rows = []
    for n in nodes_list:
        rows.append({
            "node_key": n["node_key"],
            "node_type": n["node_type"],
            "label": n["label"],
            "ref_table": n.get("ref_table"),
            "ref_id": n.get("ref_id"),
            "props": n.get("props") or {},
            "props_synced_at": n.get("props_synced_at") or now,
            "updated_at": now,
        })
    stmt = pg_insert(GraphNode).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=["node_key"],
        set_={
            "label": stmt.excluded.label,
            "props": stmt.excluded.props,
            "props_synced_at": stmt.excluded.props_synced_at,
            "updated_at": stmt.excluded.updated_at,
            "ref_table": stmt.excluded.ref_table,
            "ref_id": stmt.excluded.ref_id,
        },
    )
    db.execute(stmt)


# ---------------------------------------------------------------------------
# 边 upsert
# ---------------------------------------------------------------------------


def upsert_edge(
    db: Session,
    src_key: str,
    dst_key: str,
    rel_type: str,
    *,
    direction: str = "directed",
    weight: float = 1.0,
    confidence: float = 1.0,
    sources: Optional[list] = None,
    last_seen_by_source: Optional[dict] = None,
    evidence: Optional[dict] = None,
    last_seen: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
    first_seen: Optional[datetime] = None,
    _now: Optional[datetime] = None,  # v1.6: 允许传入 now 避免每条边都 new
) -> None:
    """幂等 upsert 一条边（以 (src_key, dst_key, rel_type) 为唯一键）。

    行为：
      - 新边：直接 INSERT（带 sources/last_seen_by_source/evidence）
      - 已存在边：合并 sources 列表（去重）+ 刷新 last_seen_by_source 时间 +
        累加 evidence.count（如有）+ 更新 confidence（取较大者）+ 更新 expires_at
    """
    sources = sources or []
    last_seen_by_source = last_seen_by_source or {}
    evidence = evidence or {}
    now = _now or datetime.now(timezone.utc)

    # 检查是否存在
    existing = (
        db.query(GraphEdge)
        .filter(
            GraphEdge.src_key == src_key,
            GraphEdge.dst_key == dst_key,
            GraphEdge.rel_type == rel_type,
        )
        .first()
    )

    if existing is None:
        # v1.6 修复：改用 pg_insert ON CONFLICT DO NOTHING 替代 db.add。
        # 原版 db.add() 在同 session 重复 add 同一 (src, dst, rel) 时，
        # flush 触发 unique 冲突而非去重。
        # DO NOTHING 让 DB 处理冲突，再 SELECT 看是否需要 UPDATE。
        stmt = (
            pg_insert(GraphEdge)
            .values(
                src_key=src_key,
                dst_key=dst_key,
                rel_type=rel_type,
                direction=direction,
                weight=weight,
                confidence=confidence,
                sources=sources,
                last_seen_by_source=last_seen_by_source,
                evidence=evidence,
                first_seen=first_seen or now,
                last_seen=last_seen or now,
                expires_at=expires_at,
            )
            .on_conflict_do_nothing(
                index_elements=["src_key", "dst_key", "rel_type"]
            )
        )
        db.execute(stmt)
        # ON CONFLICT 跳过后，existing 还是 None；如果上面真的写入了，
        # 我们就跳出（合并留给下次重建）
        return

    # 已存在：合并
    merged_sources = list(set((existing.sources or []) + sources))
    merged_lsbs = dict(existing.last_seen_by_source or {})
    merged_lsbs.update(last_seen_by_source)
    # evidence 合并：累加 count（如有），保留 sample_ids 去重
    merged_evidence = dict(existing.evidence or {})
    if evidence:
        if "count" in evidence and "count" in merged_evidence:
            try:
                merged_evidence["count"] = max(
                    merged_evidence["count"], evidence["count"])
            except (TypeError, ValueError):
                merged_evidence["count"] = evidence["count"]
        for k, v in evidence.items():
            if k in ("count", "sample_ids"):
                continue
            merged_evidence[k] = v
        # sample_ids 累加去重
        if "sample_ids" in evidence:
            old_ids = set(merged_evidence.get("sample_ids") or [])
            new_ids = old_ids | set(evidence["sample_ids"] or [])
            merged_evidence["sample_ids"] = list(new_ids)[:20]

    existing.sources = merged_sources
    existing.last_seen_by_source = merged_lsbs
    existing.evidence = merged_evidence
    existing.last_seen = last_seen or existing.last_seen or now
    if expires_at is not None:
        existing.expires_at = expires_at
    if confidence > (existing.confidence or 0):
        existing.confidence = confidence


def upsert_edges_batch(
    db: Session,
    edges: Iterable[dict],
) -> dict:
    """批量 upsert 边。返回 {"created": N, "updated": M}。

    实现：先按 (src, dst, rel_type) 去重，然后用 PostgreSQL ON CONFLICT 做 upsert。
    复杂合并（sources/evidence）放在应用层单边处理以保证正确性。
    """
    edges_list = list(edges)
    if not edges_list:
        return {"created": 0, "updated": 0}

    # 收集去重后的边键集合
    keys = {(e["src_key"], e["dst_key"], e["rel_type"]) for e in edges_list}

    created = 0
    updated = 0
    # 逐条应用层 upsert（确保 sources/evidence 合并正确）
    for edge_spec in edges_list:
        # 先查询存在性
        existing = (
            db.query(GraphEdge)
            .filter(
                GraphEdge.src_key == edge_spec["src_key"],
                GraphEdge.dst_key == edge_spec["dst_key"],
                GraphEdge.rel_type == edge_spec["rel_type"],
            )
            .first()
        )
        if existing is None:
            upsert_edge(db, **edge_spec)
            created += 1
        else:
            upsert_edge(db, **edge_spec)
            updated += 1

    return {"created": created, "updated": updated}


# ---------------------------------------------------------------------------
# 过期边清理
# ---------------------------------------------------------------------------


def delete_expired_edges(db: Session) -> int:
    """删除 expires_at < now() 的边，返回删除数量。"""
    now = datetime.now(timezone.utc)
    deleted = (
        db.query(GraphEdge)
        .filter(GraphEdge.expires_at.isnot(None))
        .filter(GraphEdge.expires_at < now)
        .delete(synchronize_session=False)
    )
    return deleted


def decay_window_for(rel_type: str) -> Optional[int]:
    """返回某类边的衰减天数（None = 不衰减）。"""
    return EDGE_DECAY_DAYS.get(rel_type)


def make_expires_at(rel_type: str, last_seen: datetime) -> Optional[datetime]:
    """根据 rel_type 的衰减窗口计算 expires_at。"""
    days = decay_window_for(rel_type)
    if days is None:
        return None
    return last_seen + timedelta(days=days)