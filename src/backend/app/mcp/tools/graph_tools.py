"""资产知识图谱 MCP tools

3 个工具：
  - get_asset_relations      取某资产 N 跳关系子图
  - find_attack_path         两节点间最短路径
  - get_impact_scope         影响面 / 爆炸半径

补齐现有 34 个工具中"零关系类"的空白，让 AI 研判（ai_analyze_alert）从
"看单条告警"升级为"看上下文子图"。

设计依据：docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6.6
"""
from __future__ import annotations

from app.mcp.tools.base import call_api


def register(mcp) -> None:
    @mcp.tool(
        name="get_asset_relations",
        description=(
            "查询资产 N 跳关系子图（节点 + 边 + 证据）。"
            "返回的节点包含资产/端口/漏洞/账号/IP/业务系统/部门/责任人/网段等；"
            "边携带 confidence（0.0-1.0）、evidence（来源表 + 计数 + 样例 id）等元数据，"
            "confidence ≥ 0.9 是已验证，0.6-0.89 是规则归一化，< 0.6 是推断（不入攻击路径）。"
            "典型问法：「192.168.0.30 关联了哪些资产？」「这台机器开放了哪些端口、有哪些漏洞？」"
            "depth ≤ 3 是常见值；limit 控制返回节点上限。"
        ),
    )
    def get_asset_relations(
        asset_id: str = "",
        depth: int = 2,
        min_conf: float = 0.5,
        rel_types: str = "",
        include_inferred: bool = True,
        limit: int = 500,
    ) -> dict:
        params: dict = {
            "depth": max(1, min(int(depth), 6)),
            "min_conf": max(0.0, min(float(min_conf), 1.0)),
            "include_inferred": bool(include_inferred),
            "limit": max(10, min(int(limit), 2000)),
        }
        if rel_types:
            params["rel_types"] = rel_types
        return call_api(
            "GET", f"/graph/assets/{asset_id}/neighbors", params=params,
        )

    @mcp.tool(
        name="find_attack_path",
        description=(
            "查找两个节点之间的最短攻击路径。"
            "只走 D1/D2 边（确定性 + 观测），不包含 D3 推断边。"
            "典型问法：「从公网入口到核心数据库有几条路径？」"
            "src/dst 接受 asset:<uuid> 或 ip:<addr> 格式；max_depth ≤ 6 是常见值。"
        ),
    )
    def find_attack_path(
        src: str = "",
        dst: str = "",
        max_depth: int = 6,
        min_conf: float = 0.7,
        max_paths: int = 10,
    ) -> dict:
        params = {
            "src": src,
            "dst": dst,
            "max_depth": max(1, min(int(max_depth), 10)),
            "min_conf": max(0.0, min(float(min_conf), 1.0)),
            "max_paths": max(1, min(int(max_paths), 100)),
        }
        return call_api("GET", "/graph/paths", params=params)

    @mcp.tool(
        name="get_impact_scope",
        description=(
            "影响面分析：给定一个或多个资产，返回 N 跳影响子图 + "
            "业务系统/责任人/重要度聚合 + 去降级判定（哪些维度缺失数据）。"
            "典型问法：「下线 192.168.0.30 影响哪些业务系统？」「这台服务器被攻陷后会涉及多少台设备？」"
            "target_keys 接受 asset:<uuid> 列表。"
        ),
    )
    def get_impact_scope(
        target_keys: list[str],
        max_depth: int = 2,
        include_inferred: bool = False,
        min_confidence: float = 0.5,
    ) -> dict:
        body = {
            "target_keys": target_keys,
            "max_depth": max(1, min(int(max_depth), 4)),
            "include_inferred": bool(include_inferred),
            "min_confidence": max(0.0, min(float(min_confidence), 1.0)),
        }
        return call_api("POST", "/graph/impact-scope", json_body=body)