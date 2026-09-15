"""
资产知识图谱 - 图查询服务（递归 CTE）

四个核心查询：
  ① neighbors           N 跳影响面（BFS，带环检测与深度上限）
  ② find_paths          两节点间最短路径（攻击路径分析）
  ③ impact_scope        影响面 + 业务系统/责任人/重要度聚合
  ④ vuln_chokepoints    修复阻塞点（choke point 修复优先级）

设计依据：docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6.4-§6.5

递归 CTE 必修坑（§5）：
  1. 必须环检测：``WHERE NOT e.dst_key = ANY(path)``，否则有环数据会跑到内存耗尽；
  2. 必须深度上限：``AND depth < N`` 作为兜底；
  3. 用 ``UNION ALL`` 而非 ``UNION``（UNION 每轮去重，慢且改变语义）。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.graph.coverage import (
    D1_D2_TYPES,
    compute_topology_coverage,
    is_attack_path_eligible,
)
from app.services.graph.utils import (
    ATTACK_EDGE_TYPES,
    INFERRED_TYPES,
    resolve_asset_or_ip_node,
)

logger = logging.getLogger(__name__)


# 统一默认参数
DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_PATHS = 10
DEFAULT_MIN_CONF = 0.5
DEFAULT_NODE_LIMIT = 500
DEFAULT_EDGE_LIMIT = 1500


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# ① 邻居子图（BFS）
# ---------------------------------------------------------------------------


def get_neighbors(
    db: Session,
    center_node_key: str,
    *,
    depth: int = 2,
    min_conf: float = DEFAULT_MIN_CONF,
    rel_types: Optional[list[str]] = None,
    include_inferred: bool = True,
    limit: int = DEFAULT_NODE_LIMIT,
) -> dict:
    """返回中心节点 N 跳邻居子图（含节点元数据 + 边证据）。

    Args:
        center_node_key: ``asset:<uuid>`` / ``ip:<addr>`` 等
        depth:           最大遍历深度（1-6，建议 ≤3）
        min_conf:        置信度门槛（< 该值的边不入子图）
        rel_types:       限定边类型列表（None=全部）
        include_inferred: 是否包含 D3 推断边（same_segment / shared_tag / co_alerted）
        limit:           返回节点上限（截断保护）

    Returns:
        {
          "center": {...},
          "nodes": [...],
          "links": [...],
          "truncated": bool,
          "stats": {...}
        }
    """
    depth = max(1, min(int(depth), 6))
    limit = max(10, min(int(limit), 5000))

    # 1. 验证中心节点存在性
    center_row = db.execute(
        text("SELECT * FROM soc_graph_nodes WHERE node_key = :k"),
        {"k": center_node_key},
    ).mappings().first()
    if not center_row:
        return {
            "center": {"id": center_node_key, "label": center_node_key, "category": "unknown"},
            "nodes": [],
            "links": [],
            "truncated": False,
            "stats": {"empty": True, "nodeCount": 0, "edgeCount": 0, "depth": depth},
            "message": f"节点不存在: {center_node_key}",
        }

    # 2. 限定边类型
    type_filter_sql = ""
    type_filter_params: dict[str, Any] = {}
    if rel_types:
        type_filter_sql = "AND e.rel_type = ANY(:rel_types)"
        type_filter_params["rel_types"] = list(rel_types)
    elif not include_inferred:
        # 排除 D3 推断边
        type_filter_sql = "AND e.rel_type <> ALL(:excl_types)"
        type_filter_params["excl_types"] = list(INFERRED_TYPES)

    # 3. 递归 CTE：BFS（带环检测 + 深度上限）
    sql = text(f"""
        WITH RECURSIVE impact AS (
            SELECT CAST(:center_key AS text) AS node_key,
                   0 AS depth,
                   ARRAY[CAST(:center_key AS text)] AS path
            UNION ALL
            SELECT e.dst_key,
                   i.depth + 1,
                   i.path || e.dst_key
            FROM soc_graph_edges e
            JOIN impact i ON e.src_key = i.node_key
            WHERE NOT e.dst_key = ANY(i.path)
              AND i.depth < :max_depth
              AND e.confidence >= :min_conf
              {type_filter_sql}
              AND (e.expires_at IS NULL OR e.expires_at > now())
        )
        SELECT DISTINCT ON (node_key)
               node_key, min(depth) OVER (PARTITION BY node_key) AS min_depth
        FROM impact
        ORDER BY node_key, min_depth
        LIMIT :node_limit
    """)

    params = {
        "center_key": center_node_key,
        "max_depth": depth,
        "min_conf": min_conf,
        "node_limit": limit,
    }
    params.update(type_filter_params)

    rows = db.execute(sql, params).mappings().all()
    reached_keys = [r["node_key"] for r in rows]
    truncated = len(rows) >= limit

    # 4. 拉节点元数据
    if not reached_keys:
        return {
            "center": _format_center_node(center_row),
            "nodes": [_format_center_node(center_row)],
            "links": [],
            "truncated": False,
            "stats": {"nodeCount": 1, "edgeCount": 0, "depth": depth,
                      "empty": True, "byRelType": {}},
        }

    nodes_rows = db.execute(
        text("SELECT * FROM soc_graph_nodes WHERE node_key = ANY(:ks)"),
        {"ks": reached_keys},
    ).mappings().all()
    nodes_by_key = {r["node_key"]: r for r in nodes_rows}

    # 5. 拉边：所有触及节点的内部边（限定方向、置信度）
    # 注意：表必须带别名 e——type_filter_sql 用的是 e.rel_type（与递归 CTE 同名），
    # 曾漏写别名导致 depth=1&include_inferred=false 时报
    # "missing FROM-clause entry for table e"（500）。
    edges_sql = text(f"""
        SELECT * FROM soc_graph_edges e
        WHERE e.src_key = ANY(:ks) AND e.dst_key = ANY(:ks)
          AND e.confidence >= :min_conf
          AND (e.expires_at IS NULL OR e.expires_at > now())
          {type_filter_sql}
        ORDER BY e.confidence DESC, e.last_seen DESC NULLS LAST
        LIMIT :edge_limit
    """)
    edge_params = {
        "ks": reached_keys,
        "min_conf": min_conf,
        "edge_limit": DEFAULT_EDGE_LIMIT,
    }
    edge_params.update(type_filter_params)
    edge_rows = db.execute(edges_sql, edge_params).mappings().all()

    # 6. 序列化 + 统计
    nodes = []
    for k in reached_keys:
        r = nodes_by_key.get(k)
        nodes.append(_format_graph_node(r, k))

    links = []
    by_rel_type: dict[str, int] = defaultdict(int)
    by_conf: dict[str, int] = defaultdict(int)
    for e in edge_rows:
        links.append(_format_graph_edge(e))
        by_rel_type[e["rel_type"]] += 1
        bucket = _conf_bucket(float(e["confidence"] or 0))
        by_conf[bucket] += 1

    return {
        "center": _format_center_node(center_row),
        "nodes": nodes,
        "links": links,
        "truncated": truncated,
        "stats": {
            "nodeCount": len(nodes),
            "edgeCount": len(links),
            "depth": depth,
            "byRelType": dict(by_rel_type),
            "byConfidence": dict(by_conf),
        },
    }


# ---------------------------------------------------------------------------
# ② 最短路径查询（攻击路径）
# ---------------------------------------------------------------------------


def find_paths(
    db: Session,
    src_key: str,
    dst_key: str,
    *,
    max_depth: int = 6,
    min_conf: float = 0.7,
    max_paths: int = DEFAULT_MAX_PATHS,
) -> dict:
    """查找 src_key → dst_key 的所有最短路径（D1/D2 边可入攻击路径）。

    Args:
        src_key:     源节点
        dst_key:     目标节点
        max_depth:   最大路径长度（跳数）
        min_conf:    边置信度门槛
        max_paths:   最多返回路径数

    Returns:
        {"paths": [{"nodeKeys": [...], "edges": [...], "cost": float, "minConfidence": float}],
         "stats": {"pathCount": N, "minCost": float, "maxDepthUsed": N}}
    """
    max_depth = max(1, min(int(max_depth), 10))
    max_paths = max(1, min(int(max_paths), 100))

    # 递归前向搜索（src → dst）
    sql = text("""
        WITH RECURSIVE paths AS (
            SELECT e.dst_key AS node_key,
                   1 AS depth,
                   ARRAY[e.src_key, e.dst_key] AS path,
                   ARRAY[e.id]::uuid[] AS edge_ids,
                   e.weight AS cost,
                   e.confidence AS min_conf,
                   e.rel_type AS last_rel
            FROM soc_graph_edges e
            WHERE e.src_key = :src
              AND e.rel_type = ANY(:attack_types)
              AND e.confidence >= :min_conf
              AND (e.expires_at IS NULL OR e.expires_at > now())
            UNION ALL
            SELECT e.dst_key,
                   p.depth + 1,
                   p.path || e.dst_key,
                   p.edge_ids || e.id,
                   (p.cost + e.weight)::numeric(5,3),
                   LEAST(p.min_conf, e.confidence),
                   e.rel_type
            FROM soc_graph_edges e
            JOIN paths p ON e.src_key = p.node_key
            WHERE NOT e.dst_key = ANY(p.path)
              AND p.depth < :max_depth
              AND e.rel_type = ANY(:attack_types)
              AND e.confidence >= :min_conf
              AND (e.expires_at IS NULL OR e.expires_at > now())
        )
        SELECT path, edge_ids, cost, min_conf, depth
        FROM paths
        WHERE node_key = :dst
        ORDER BY cost ASC, min_conf DESC
        LIMIT :max_paths
    """)

    attack_types = list(ATTACK_EDGE_TYPES)
    rows = db.execute(sql, {
        "src": src_key,
        "dst": dst_key,
        "max_depth": max_depth,
        "min_conf": min_conf,
        "max_paths": max_paths,
        "attack_types": attack_types,
    }).mappings().all()

    if not rows:
        return {
            "paths": [],
            "stats": {"pathCount": 0, "minCost": None, "maxDepthUsed": 0},
            "message": f"未找到 {src_key} → {dst_key} 的路径",
        }

    # 拉边明细
    all_edge_ids = []
    for r in rows:
        all_edge_ids.extend(r["edge_ids"])
    edge_meta: dict = {}
    if all_edge_ids:
        for e in db.execute(
            text("SELECT * FROM soc_graph_edges WHERE id = ANY(:ids)"),
            {"ids": list(set(all_edge_ids))},
        ).mappings().all():
            edge_meta[str(e["id"])] = e

    # 组装结果
    paths = []
    for r in rows:
        edge_specs = []
        for eid in r["edge_ids"]:
            e = edge_meta.get(str(eid))
            if e:
                edge_specs.append({
                    "relType": e["rel_type"],
                    "confidence": float(e["confidence"] or 0),
                    "srcKey": e["src_key"],
                    "dstKey": e["dst_key"],
                })
        paths.append({
            "nodeKeys": r["path"],
            "edges": edge_specs,
            "cost": float(r["cost"]),
            "minConfidence": float(r["min_conf"]),
            "depth": r["depth"],
        })

    return {
        "paths": paths,
        "stats": {
            "pathCount": len(paths),
            "minCost": min(p["cost"] for p in paths),
            "maxDepthUsed": max(p["depth"] for p in paths),
        },
    }


# ---------------------------------------------------------------------------
# ③ 影响面（impact_scope）
# ---------------------------------------------------------------------------


def impact_scope(
    db: Session,
    target_keys: list[str],
    *,
    max_depth: int = 2,
    min_confidence: float = DEFAULT_MIN_CONF,
    include_inferred: bool = False,
    node_limit: int = DEFAULT_NODE_LIMIT,
) -> dict:
    """影响面分析：返回目标资产 + N 跳子图 + 业务系统/责任人/重要度聚合。

    Args:
        target_keys:       目标节点列表（通常 1-3 个核心资产）
        max_depth:         遍历深度
        min_confidence:    边置信度门槛
        include_inferred:  是否包含 D3 推断边
        node_limit:        节点上限

    Returns:
        {
          "scope": {
            "nodes": [...], "links": [...],
            "byBusinessSystem": {"<system>": count},
            "byOwner":         {"<user>": count},
            "byCriticality":   {"critical": N, ...},
          },
          "warnings": [{"code", "message", "count"}],
          "degraded": bool,
          "message": "..."
        }
    """
    # 收集所有目标节点的子图（合并去重）
    all_node_keys: set[str] = set()
    all_links: list[dict] = []
    for tk in target_keys:
        sub = get_neighbors(
            db, tk,
            depth=max_depth,
            min_conf=min_confidence,
            include_inferred=include_inferred,
            limit=node_limit,
        )
        for n in sub["nodes"]:
            all_node_keys.add(n["id"])
        # links 取两端都在合并节点集内的
        nk_set = {n["id"] for n in sub["nodes"]}
        for link in sub["links"]:
            if link["source"] in nk_set and link["target"] in nk_set:
                # 去重
                edge_key = (link["source"], link["target"], link["relType"])
                if not any(
                    (l["source"], l["target"], l["relType"]) == edge_key
                    for l in all_links
                ):
                    all_links.append(link)

    # 拉节点元数据
    nodes_rows = db.execute(
        text("SELECT * FROM soc_graph_nodes WHERE node_key = ANY(:ks)"),
        {"ks": list(all_node_keys)},
    ).mappings().all()
    nodes = [_format_graph_node(r, r["node_key"]) for r in nodes_rows]

    # 拉涉及的资产节点
    asset_node_keys = [
        r["node_key"] for r in nodes_rows if r["node_type"] == "asset"
    ]
    asset_ids = []
    for k in asset_node_keys:
        if k.startswith("asset:"):
            try:
                asset_ids.append(k.split(":", 1)[1])
            except (IndexError, ValueError):
                continue

    by_business: dict[str, int] = defaultdict(int)
    by_owner: dict[str, int] = defaultdict(int)
    by_criticality: dict[str, int] = defaultdict(int)
    if asset_ids:
        # 业务系统归属
        for r in db.execute(
            text("""
                SELECT ab.asset_id, bs.name as system_name
                FROM soc_asset_business ab
                JOIN soc_business_systems bs ON bs.id = ab.system_id
                WHERE ab.asset_id::text = ANY(:aids)
            """),
            {"aids": asset_ids},
        ).mappings().all():
            by_business[r["system_name"] or "(unknown)"] += 1
        # 责任人
        for r in db.execute(
            text("""
                SELECT a.id, u.username, u.full_name
                FROM soc_assets a
                LEFT JOIN soc_users u ON u.id = a.owner_id
                WHERE a.id::text = ANY(:aids)
            """),
            {"aids": asset_ids},
        ).mappings().all():
            name = r["full_name"] or r["username"] or "(unowned)"
            by_owner[name] += 1
        # 重要度
        for r in db.execute(
            text("""
                SELECT id, criticality FROM soc_assets
                WHERE id::text = ANY(:aids)
            """),
            {"aids": asset_ids},
        ).mappings().all():
            by_criticality[r["criticality"] or "medium"] += 1

    # 去降级判定（基于本次拉到的边）
    edge_objs = db.execute(
        text("SELECT rel_type, confidence FROM soc_graph_edges "
             "WHERE src_key = ANY(:ks) AND dst_key = ANY(:ks)"),
        {"ks": list(all_node_keys)},
    ).mappings().all()

    # 包装成 GraphEdge-like 对象给 compute_topology_coverage
    class _E:
        def __init__(self, rel_type, confidence):
            self.rel_type = rel_type
            self.confidence = confidence
    coverage = compute_topology_coverage([_E(r["rel_type"], r["confidence"])
                                          for r in edge_objs])

    # 把 coverage 的警告补 count（命中数）
    warnings_with_count: list[dict] = []
    for w in coverage["warnings"]:
        warnings_with_count.append({
            **w,
            "count": _count_warning(db, w["code"], asset_ids),
        })

    degraded = coverage["degraded"]
    if degraded:
        msg_parts = [w["message"] for w in warnings_with_count]
        message = "完整拓扑" if not msg_parts else "数据不完整：" + "；".join(msg_parts)
    else:
        message = "完整拓扑（端口+业务系统+责任人齐全）"

    return {
        "scope": {
            "nodes": nodes,
            "links": all_links,
            "byBusinessSystem": dict(by_business),
            "byOwner": dict(by_owner),
            "byCriticality": dict(by_criticality),
        },
        "warnings": warnings_with_count,
        "degraded": degraded,
        "score": coverage["score"],
        "message": message,
    }


def _count_warning(db: Session, code: str, asset_ids: list[str]) -> int:
    """计算某 warning 的命中数（粗略）。"""
    if code == "MISSING_OWNER":
        n = db.execute(
            text("SELECT count(*) AS c FROM soc_assets "
                 "WHERE id::text = ANY(:aids) AND (owner_id IS NULL AND (owner IS NULL OR owner = ''))"),
            {"aids": asset_ids},
        ).scalar() or 0
        return int(n)
    if code == "MISSING_BIZ":
        n = db.execute(
            text("""
                SELECT count(*) AS c FROM soc_assets a
                WHERE a.id::text = ANY(:aids)
                  AND NOT EXISTS (
                      SELECT 1 FROM soc_asset_business ab
                      WHERE ab.asset_id = a.id
                  )
            """),
            {"aids": asset_ids},
        ).scalar() or 0
        return int(n)
    if code == "MISSING_HAS_PORT":
        n = db.execute(
            text("""
                SELECT count(*) AS c FROM soc_assets a
                WHERE a.id::text = ANY(:aids)
                  AND NOT EXISTS (
                      SELECT 1 FROM soc_asset_ports p
                      WHERE p.asset_id = a.id
                  )
            """),
            {"aids": asset_ids},
        ).scalar() or 0
        return int(n)
    return 0


# ---------------------------------------------------------------------------
# ④ Choke Point（修复优先级）
# ---------------------------------------------------------------------------


def vuln_chokepoints(
    db: Session,
    *,
    limit: int = 20,
    max_depth: int = 3,
    min_conf: float = 0.7,
    criticality_filter: Optional[list[str]] = None,
) -> dict:
    """漏洞修复阻塞点：出现在最多攻击路径上的漏洞 → 修一个断多条。

    算法（§6.4-③ 近似度数中心性）：
      1) 找出 critical/high 资产集合
      2) 对每个高价值资产反向做 N 跳可达集
      3) 统计可达集内各 vulnerability 节点出现的次数
      4) 按 count 倒序排列 = 修复优先级

    Returns:
        {"chokepoints": [{"vulnKey", "cveId", "cvss", "severity",
                          "reachableCriticalCount", "reachableAssets"}],
         "method": "approximate_degree_centrality",
         "params": {...}}
    """
    criticality_filter = criticality_filter or ["critical", "high"]

    # 1. 找高价值资产节点
    asset_rows = db.execute(
        text("""
            SELECT id FROM soc_assets
            WHERE criticality = ANY(:crits)
        """),
        {"crits": criticality_filter},
    ).mappings().all()
    crown_assets = [f"asset:{r['id']}" for r in asset_rows]

    if not crown_assets:
        return {
            "chokepoints": [],
            "method": "approximate_degree_centrality",
            "params": {"max_depth": max_depth, "min_conf": min_conf,
                       "criticality_filter": criticality_filter},
            "message": "无 critical/high 资产",
        }

    # 2. 反向 BFS（从 crown 出发，收集 N 跳可达的 vuln 节点）
    vuln_count: dict[str, int] = defaultdict(int)
    vuln_critical_assets: dict[str, set] = defaultdict(set)

    for crown in crown_assets:
        sql = text("""
            WITH RECURSIVE reach AS (
                SELECT CAST(:crown AS text) AS node_key, 0 AS depth,
                       ARRAY[CAST(:crown AS text)] AS path
                UNION ALL
                SELECT e.dst_key, r.depth + 1, r.path || e.dst_key
                FROM soc_graph_edges e
                JOIN reach r ON e.src_key = r.node_key
                WHERE NOT e.dst_key = ANY(r.path)
                  AND r.depth < :max_depth
                  AND e.confidence >= :min_conf
                  AND e.rel_type = ANY(:attack_types)
                  AND (e.expires_at IS NULL OR e.expires_at > now())
            )
            SELECT node_key FROM reach WHERE node_key LIKE 'vuln:%'
        """)
        rows = db.execute(sql, {
            "crown": crown,
            "max_depth": max_depth,
            "min_conf": min_conf,
            "attack_types": list(ATTACK_EDGE_TYPES),
        }).mappings().all()
        for r in rows:
            vuln_count[r["node_key"]] += 1
            vuln_critical_assets[r["node_key"]].add(crown)

    # 3. 拉 vulnerability 元数据
    vuln_keys = list(vuln_count.keys())
    if not vuln_keys:
        return {
            "chokepoints": [],
            "method": "approximate_degree_centrality",
            "params": {"max_depth": max_depth, "min_conf": min_conf,
                       "criticality_filter": criticality_filter},
        }

    vuln_meta_rows = db.execute(
        text("""
            SELECT n.node_key, n.props, v.cve_id, v.cvss_score, v.severity
            FROM soc_graph_nodes n
            LEFT JOIN soc_vulnerabilities v
              ON n.ref_id::uuid = v.id
            WHERE n.node_key = ANY(:ks)
        """),
        {"ks": vuln_keys},
    ).mappings().all()

    chokepoints = []
    for r in vuln_meta_rows:
        count = vuln_count.get(r["node_key"], 0)
        props = r.get("props") or {}
        cve = r.get("cve_id") or props.get("cve_id") or r["node_key"]
        cvss = r.get("cvss_score")
        cvss = float(cvss) if cvss is not None else float(props.get("cvss") or 0)
        severity = r.get("severity") or props.get("severity") or "unknown"
        chokepoints.append({
            "vulnKey": r["node_key"],
            "cveId": cve,
            "cvss": cvss,
            "severity": severity,
            "reachableCriticalCount": count,
            "reachableAssets": sorted(vuln_critical_assets[r["node_key"]])[:20],
        })

    # 按可达 critical 资产数倒序
    chokepoints.sort(key=lambda x: -x["reachableCriticalCount"])
    chokepoints = chokepoints[:limit]

    return {
        "chokepoints": chokepoints,
        "method": "approximate_degree_centrality",
        "params": {
            "max_depth": max_depth,
            "min_conf": min_conf,
            "criticality_filter": criticality_filter,
        },
    }


# ---------------------------------------------------------------------------
# ⑤ 全图统计
# ---------------------------------------------------------------------------


def graph_stats(db: Session) -> dict:
    """返回图谱整体统计：节点/边数、按类型分布、按置信度分布、覆盖率。"""
    nodes_total = db.execute(text("SELECT count(*) FROM soc_graph_nodes")).scalar() or 0
    edges_total = db.execute(text("SELECT count(*) FROM soc_graph_edges")).scalar() or 0

    # 节点类型
    nodes_by_type = dict(db.execute(text("""
        SELECT node_type, count(*) AS c FROM soc_graph_nodes
        GROUP BY node_type
    """)).mappings().all())

    # 边类型
    edges_by_rel = dict(db.execute(text("""
        SELECT rel_type, count(*) AS c FROM soc_graph_edges
        GROUP BY rel_type
    """)).mappings().all())

    # 置信度分桶
    edges_by_conf = dict(db.execute(text("""
        SELECT
            CASE
                WHEN confidence >= 0.9 THEN '1.0'
                WHEN confidence >= 0.8 THEN '0.9'
                WHEN confidence >= 0.7 THEN '0.8'
                WHEN confidence >= 0.6 THEN '0.7'
                WHEN confidence >= 0.5 THEN '0.5'
                WHEN confidence >= 0.4 THEN '0.4'
                ELSE '0.0'
            END AS bucket,
            count(*) AS c
        FROM soc_graph_edges
        GROUP BY bucket
    """)).mappings().all())

    # 活跃边（未过期）
    active_after_expiry = db.execute(text("""
        SELECT count(*) FROM soc_graph_edges
        WHERE expires_at IS NOT NULL AND expires_at > now()
    """)).scalar() or 0

    # 覆盖率
    assets_total = db.execute(text("SELECT count(*) FROM soc_assets")).scalar() or 0
    assets_with_any_edge = db.execute(text("""
        SELECT count(DISTINCT node_key) FROM soc_graph_nodes
        WHERE node_type = 'asset'
          AND node_key IN (
              SELECT src_key FROM soc_graph_edges
              UNION
              SELECT dst_key FROM soc_graph_edges
          )
    """)).scalar() or 0

    assets_with_d1d2 = db.execute(text("""
        SELECT count(DISTINCT n.node_key) FROM soc_graph_nodes n
        WHERE n.node_type = 'asset'
          AND (
              EXISTS (SELECT 1 FROM soc_graph_edges e
                      WHERE (e.src_key = n.node_key OR e.dst_key = n.node_key)
                        AND e.rel_type = ANY(:types))
          )
    """), {"types": list(D1_D2_TYPES)}).scalar() or 0

    critical_with_owner = db.execute(text("""
        SELECT count(*) FROM soc_assets
        WHERE criticality IN ('critical', 'high')
          AND owner_id IS NOT NULL
    """)).scalar() or 0
    critical_total = db.execute(text("""
        SELECT count(*) FROM soc_assets
        WHERE criticality IN ('critical', 'high')
    """)).scalar() or 0

    assets_with_biz = db.execute(text("""
        SELECT count(DISTINCT asset_id) FROM soc_asset_business
    """)).scalar() or 0

    return {
        "nodes": {
            "total": nodes_total,
            "byType": nodes_by_type,
        },
        "edges": {
            "total": edges_total,
            "byRelType": edges_by_rel,
            "byConfidence": edges_by_conf,
            "activeAfterExpiry": active_after_expiry,
        },
        "coverage": {
            "assetsTotal": assets_total,
            "assetsWithAnyEdge": assets_with_any_edge,
            "assetsWithD1D2Edges": assets_with_d1d2,
            "criticalAssetsWithOwner": critical_with_owner,
            "criticalAssetsTotal": critical_total,
            "assetsWithBusinessSystem": assets_with_biz,
        },
        "health": {
            "queried_at": _utcnow().isoformat(),
        },
    }


# ---------------------------------------------------------------------------
# 内部：序列化辅助
# ---------------------------------------------------------------------------


def _format_graph_node(row, fallback_key: str) -> dict:
    """GraphNode 行 → API 字典。"""
    if not row:
        return {
            "id": fallback_key,
            "label": fallback_key,
            "category": fallback_key.split(":", 1)[0] if ":" in fallback_key else "unknown",
            "rawProps": {},
        }
    return {
        "id": row["node_key"],
        "label": row["label"] or row["node_key"],
        "category": row["node_type"],
        "rawProps": row.get("props") or {},
    }


def _format_center_node(row) -> dict:
    return {
        "id": row["node_key"],
        "label": row["label"] or row["node_key"],
        "category": row["node_type"],
        "rawProps": row.get("props") or {},
    }


def _format_graph_edge(row) -> dict:
    """GraphEdge 行 → API 字典（含视觉编码）。

    视觉编码（§6.5.2）：
      - conf ≥ 0.9  → 实线深色
      - conf 0.6-0.89 → 实线浅色
      - conf < 0.6  → 虚线灰色（D3 推断）
    """
    conf = float(row["confidence"] or 0)
    rel = row["rel_type"]
    if conf >= 0.9:
        line_style = {"color": "#A32D2D", "width": 2.5, "type": "solid"}
    elif conf >= 0.6:
        line_style = {"color": "#5B6E8C", "width": 1.5, "type": "solid"}
    else:
        line_style = {"color": "#9CA3AF", "width": 1.0, "type": "dashed"}

    return {
        "id": str(row["id"]),
        "source": row["src_key"],
        "target": row["dst_key"],
        "relType": rel,
        "confidence": conf,
        "weight": float(row["weight"] or 1),
        "direction": row["direction"],
        "lineStyle": line_style,
        "evidence": row.get("evidence") or {},
        "sourceLabel": _source_label(row.get("sources") or []),
        "updated": row["updated_at"].isoformat() if row.get("updated_at") else None,
        "firstSeen": row["first_seen"].isoformat() if row.get("first_seen") else None,
        "lastSeen": row["last_seen"].isoformat() if row.get("last_seen") else None,
        "sources": list(row.get("sources") or []),
    }


def _source_label(sources: Iterable[str]) -> str:
    """边 sources 列表 → 前端展示字符串。"""
    items = list(sources)
    if not items:
        return "未知"
    if "manual" in items:
        return "人工登记"
    if "inferred:network_segment" in items or "inferred:tag" in items:
        return "推断"
    if "soc_assets.owner_id" in items or "soc_assets.parent_id" in items:
        return "资产关系"
    if "soc_business_systems.owner_id" in items or "soc_asset_business" in items:
        return "业务关系"
    if "soc_alert_groups" in items:
        return "告警聚合"
    if "wazuh" in items:
        return "Wazuh"
    return " / ".join(items[:2])


def _conf_bucket(conf: float) -> str:
    if conf >= 0.9:
        return "1.0"
    if conf >= 0.8:
        return "0.9"
    if conf >= 0.7:
        return "0.8"
    if conf >= 0.5:
        return "0.5"
    if conf >= 0.4:
        return "0.4"
    return "0.0"