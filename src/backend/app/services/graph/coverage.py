"""
图谱覆盖率与去降级判定

核心职责：
  - D1/D2 边类型清单（用于判定是否能进入攻击路径）
  - ``compute_topology_coverage`` 评估单次分析的去降级状态

设计依据：docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6.7.3
"""
from __future__ import annotations

from typing import Iterable, Sequence

# 同步自 utils（避免循环导入）
from app.services.graph.utils import D1_TYPES, D2_TYPES


# D1 + D2 = 可入攻击路径计算；用于覆盖度判定
D1_D2_TYPES: set[str] = D1_TYPES | D2_TYPES


def compute_topology_coverage(edges: Sequence) -> dict:
    """返回单资产 / 单次分析的去降级判定结果。

    算法（§6.7.3 精确公式）：
      - 检查三类核心 D1/D2 边是否齐备：has_port / belongs_to_system / owned_by
      - 加分项：login_to + has_vuln 同时存在（决定攻击路径可用性）
      - 任一缺失 → degraded=True + 对应 warning

    Args:
        edges: GraphEdge 对象列表（已过滤 expired + min_conf 门槛）

    Returns:
        {
          "degraded": bool,
          "warnings": [{"code": "...", "message": "..."}],
          "score": float in [0, 1]
        }
    """
    d1d2 = [e for e in edges if e.rel_type in D1_D2_TYPES and (e.confidence or 0) >= 0.7]
    present = {e.rel_type for e in d1d2}

    # 三类核心边检查
    checks = [
        ("has_port", "无开放端口/服务版本数据，无法评估攻击面"),
        ("belongs_to_system", "无业务系统归属，无法评估变更影响面"),
        ("owned_by", "无责任人归属，变更通知无法触达"),
    ]
    warnings = [
        {"code": f"MISSING_{rt.upper()}", "message": msg}
        for rt, msg in checks if rt not in present
    ]

    # 加分项：login_to + has_vuln（决定攻击路径的可达性 / 可利用性）
    bonus_ok = {"login_to", "has_vuln"}.issubset(present)

    # degraded 判定：任何核心缺失 OR 加分项缺失
    degraded = len(warnings) > 0 or not bonus_ok

    max_score = len(checks) + 1  # 3 个核心 + 1 个加分项 = 4
    actual = (len(checks) - len(warnings)) + (1 if bonus_ok else 0)
    score = round(actual / max_score, 2) if max_score else 0.0

    return {
        "degraded": degraded,
        "warnings": warnings,
        "score": score,
        "present_edge_types": sorted(present),
        "checked": [c[0] for c in checks],
        "bonus_ok": bonus_ok,
    }


def edge_type_category(rel_type: str) -> str:
    """返回边类型所属分档（D1/D2/D3/D4/other）。"""
    if rel_type in D1_TYPES:
        return "D1"
    if rel_type in D2_TYPES:
        return "D2"
    if rel_type in {"same_segment", "shared_tag", "co_alerted"}:
        return "D3"
    if rel_type == "depends_on":
        return "D4"
    return "other"


def is_attack_path_eligible(rel_type: str, confidence: float, min_conf: float = 0.7) -> bool:
    """判定某条边是否可以进入攻击路径计算。

    规则：D1/D2 分档 + confidence ≥ 门槛（默认 0.7）。
    """
    return rel_type in D1_D2_TYPES and (confidence or 0) >= min_conf