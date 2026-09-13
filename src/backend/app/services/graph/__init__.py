"""资产知识图谱服务包（G1）

子模块：
  - utils:        节点归并 / 外部 IP 判定 / 通用 upsert 工具
  - builders:     5 个边构建器（资产-端口-漏洞 / 身份 / 拓扑 / 告警簇 / 人工）
  - query:        4 个图查询（neighbors / paths / impact_scope / vuln_chokepoints）
  - coverage:     去降级判定（compute_topology_coverage）
  - sync_props:   节点 props 快照同步
  - scheduler:    @track_task 包装的定时任务入口

设计依据：docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6
"""
from .utils import (
    resolve_asset_or_ip_node,
    is_external_ip,
    ensure_node,
    ensure_nodes_batch,
    upsert_edge,
    upsert_edges_batch,
    delete_expired_edges,
    EDGE_DECAY_DAYS,
)
from .coverage import compute_topology_coverage, D1_D2_TYPES
from . import scheduler

__all__ = [
    # utils
    "resolve_asset_or_ip_node",
    "is_external_ip",
    "ensure_node",
    "ensure_nodes_batch",
    "upsert_edge",
    "upsert_edges_batch",
    "delete_expired_edges",
    "EDGE_DECAY_DAYS",
    # coverage
    "compute_topology_coverage",
    "D1_D2_TYPES",
    # scheduler
    "scheduler",
]