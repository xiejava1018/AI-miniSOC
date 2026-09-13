"""
资产知识图谱 API（PRD P5 / 知识图谱）

端点（前缀 /api/v1/graph）：
  GET  /assets/{id}/neighbors              邻居子图
  GET  /paths                              最短路径
  POST /impact-scope                       影响面
  GET  /vuln-chokepoints                   修复阻塞点
  GET  /stats                              全图统计
  POST /relations                          人工登记关系
  POST /rebuild                            触发重建

注意：
  - envelope: {code, msg, data}（与项目惯例一致，HTTP 200 + 业务码）
  - 字段命名：snake_case（API JSON）；前端 TS 转 camelCase
  - ECharts 对齐：API 返回 data.nodes / data.links 直接对应 ECharts series
  - 截断保护：默认 500 节点 / 1500 边上限
  - 空态：data = {nodes:[], links:[], stats:{empty:true}, message:"..."}

设计依据：docs/design/2026-09-13-资产知识图谱研究与实施方案.md §6.5
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from app.core.permissions import require_role
from app.core.database import get_db
from app.models import Asset, User
from app.services.graph import (
    delete_expired_edges,
)
from app.services.graph.builders import (
    AlertGroupBuilder,
    AssetPortVulnBuilder,
    IdentityGraphBuilder,
    ManualRelationBuilder,
    TopologyBuilder,
)
from app.services.graph.query import (
    find_paths,
    get_neighbors,
    graph_stats,
    impact_scope,
    vuln_chokepoints,
)
from app.services.graph.utils import (
    ensure_node,
    upsert_edge,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# 公共：参数校验
# ---------------------------------------------------------------------------

_NODE_KEY_RE = re.compile(r"^[a-z_]+:[A-Za-z0-9_\-./:]+$")


def _validate_node_key(node_key: str) -> str:
    """校验 node_key 格式（type:identifier），避免任意字符串入图。"""
    if not node_key or len(node_key) > 200:
        raise HTTPException(status_code=400,
                            detail=f"无效 node_key: {node_key[:50]}")
    if not _NODE_KEY_RE.match(node_key):
        raise HTTPException(status_code=400,
                            detail=f"node_key 格式错误（须为 type:identifier）: {node_key[:50]}")
    return node_key


def _resolve_asset_key(db: Session, asset_id: str) -> str:
    """asset UUID → asset:<uuid>。校验存在性。"""
    try:
        UUID(asset_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail=f"asset_id 非法: {asset_id}")
    a = db.query(Asset).filter(Asset.id == asset_id).first()
    if not a:
        raise HTTPException(status_code=404, detail=f"资产不存在: {asset_id}")
    return f"asset:{asset_id}"


# ---------------------------------------------------------------------------
# ① GET /api/v1/graph/assets/{id}/neighbors
# ---------------------------------------------------------------------------


@router.get("/assets/{asset_id}/neighbors", summary="资产 N 跳邻居子图")
async def get_asset_neighbors(
    asset_id: str,
    depth: int = Query(2, ge=1, le=6, description="最大遍历深度（1-6，建议 ≤3）"),
    min_conf: float = Query(0.5, ge=0, le=1, description="边置信度门槛"),
    rel_types: Optional[str] = Query(None, description="限定边类型（逗号分隔）"),
    include_inferred: bool = Query(True, description="是否包含 D3 推断边"),
    limit: int = Query(500, ge=10, le=2000, description="节点上限"),
    db: Session = Depends(get_db),
):
    """返回某资产的 N 跳关系子图（用于前端 ECharts 渲染）。"""
    center_key = _resolve_asset_key(db, asset_id)

    types_list = None
    if rel_types:
        types_list = [t.strip() for t in rel_types.split(",") if t.strip()]

    result = get_neighbors(
        db, center_key,
        depth=depth, min_conf=min_conf,
        rel_types=types_list,
        include_inferred=include_inferred,
        limit=limit,
    )

    if result.get("stats", {}).get("empty"):
        return {"code": 200, "msg": "ok",
                "data": {**result, "message": result.get("message", "无数据")}}

    return {"code": 200, "msg": "ok", "data": result}


# ---------------------------------------------------------------------------
# ② GET /api/v1/graph/paths
# ---------------------------------------------------------------------------


@router.get("/paths", summary="最短攻击路径查询")
async def get_paths(
    src: str = Query(..., description="源节点（如 asset:<uuid> 或 ip:<addr>）"),
    dst: str = Query(..., description="目标节点（同上）"),
    max_depth: int = Query(6, ge=1, le=10),
    min_conf: float = Query(0.7, ge=0, le=1),
    max_paths: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """两节点间最短攻击路径（D1/D2 边）。"""
    src_key = _validate_node_key(src)
    dst_key = _validate_node_key(dst)
    result = find_paths(
        db, src_key, dst_key,
        max_depth=max_depth, min_conf=min_conf, max_paths=max_paths,
    )
    return {"code": 200, "msg": "ok", "data": result}


# ---------------------------------------------------------------------------
# ③ POST /api/v1/graph/impact-scope
# ---------------------------------------------------------------------------


class ImpactScopeRequest(BaseModel):
    target_keys: list[str] = Field(..., min_length=1, max_length=20,
                                    description="目标节点列表（asset:<uuid> 或 ip:<addr>）")
    max_depth: int = Field(2, ge=1, le=4, description="遍历深度")
    include_inferred: bool = Field(False, description="是否包含 D3 推断边")
    min_confidence: float = Field(0.5, ge=0, le=1)

    @validator("target_keys")
    def _validate_keys(cls, v):
        for k in v:
            if not _NODE_KEY_RE.match(k):
                raise ValueError(f"无效的 node_key: {k[:50]}")
        return v


@router.post("/impact-scope", summary="影响面分析")
async def post_impact_scope(
    body: ImpactScopeRequest,
    db: Session = Depends(get_db),
):
    """多资产影响面聚合（含业务系统/责任人/重要度分布 + 去降级判定）。"""
    result = impact_scope(
        db, body.target_keys,
        max_depth=body.max_depth,
        min_confidence=body.min_confidence,
        include_inferred=body.include_inferred,
    )
    return {"code": 200, "msg": "ok", "data": result}


# ---------------------------------------------------------------------------
# ④ GET /api/v1/graph/vuln-chokepoints
# ---------------------------------------------------------------------------


@router.get("/vuln-chokepoints", summary="漏洞修复阻塞点（choke point）")
async def get_vuln_chokepoints(
    limit: int = Query(20, ge=1, le=100),
    max_depth: int = Query(3, ge=1, le=6),
    min_conf: float = Query(0.7, ge=0, le=1),
    criticality: Optional[str] = Query(None, description="critical/high（逗号分隔）"),
    db: Session = Depends(get_db),
):
    """按"出现在最多攻击路径上"对漏洞排序，修一个断多条。"""
    crit = None
    if criticality:
        crit = [c.strip() for c in criticality.split(",") if c.strip()]

    result = vuln_chokepoints(
        db, limit=limit, max_depth=max_depth,
        min_conf=min_conf, criticality_filter=crit,
    )
    return {"code": 200, "msg": "ok", "data": result}


# ---------------------------------------------------------------------------
# ⑤ GET /api/v1/graph/stats
# ---------------------------------------------------------------------------


@router.get("/stats", summary="图谱整体统计")
async def get_graph_stats(
    db: Session = Depends(get_db),
):
    """节点/边数、按类型分布、按置信度分布、覆盖率、健康度。"""
    result = graph_stats(db)
    return {"code": 200, "msg": "ok", "data": result}


# ---------------------------------------------------------------------------
# ⑥ POST /api/v1/graph/relations（人工登记关系）
# ---------------------------------------------------------------------------


class RelationRequest(BaseModel):
    src_key: str
    dst_key: str
    rel_type: str
    weight: float = Field(1.0, ge=0, le=100)
    confidence: float = Field(1.0, ge=0, le=1)
    direction: str = Field("directed", pattern="^(directed|undirected)$")
    evidence: dict[str, Any] = Field(default_factory=dict)

    @validator("src_key", "dst_key")
    def _validate_keys(cls, v):
        return _validate_node_key(v)

    @validator("rel_type")
    def _validate_rel(cls, v):
        allowed = {
            "has_port", "has_vuln", "port_has_vuln",
            "belongs_to_system", "owned_by", "system_owned_by", "runs_on",
            "login_to", "login_from", "session_on", "external_access",
            "same_segment", "shared_tag", "alerted_on", "co_alerted",
            "depends_on",
        }
        if v not in allowed:
            raise ValueError(f"未允许的 rel_type: {v}")
        return v


@router.post("/relations", summary="人工登记关系",
              dependencies=[Depends(require_role("admin", "operator"))])
async def post_relation(
    body: RelationRequest,
    db: Session = Depends(get_db),
):
    """人工登记一条关系边（D1/D4 类）。"""
    # 自动确保 src / dst 节点存在（若不存在则创建 minimal 节点）
    src_kind = body.src_key.split(":", 1)[0]
    dst_kind = body.dst_key.split(":", 1)[0]
    ensure_node(db, body.src_key, src_kind, body.src_key,
               props={"manual_registered_by": current_user.username})
    ensure_node(db, body.dst_key, dst_kind, body.dst_key,
               props={"manual_registered_by": current_user.username})

    # 在 evidence 加上登记人
    evidence = dict(body.evidence or {})
    evidence.setdefault("registered_by", current_user.username)
    evidence["registered_at"] = __import__("datetime").datetime.utcnow().isoformat()

    upsert_edge(
        db, body.src_key, body.dst_key, body.rel_type,
        direction=body.direction,
        weight=body.weight,
        confidence=body.confidence,
        sources=["manual"],
        evidence=evidence,
    )
    db.commit()
    return {"code": 201, "msg": "ok",
            "data": {"src_key": body.src_key, "dst_key": body.dst_key,
                     "rel_type": body.rel_type}}


# ---------------------------------------------------------------------------
# ⑦ POST /api/v1/graph/rebuild（触发重建）
# ---------------------------------------------------------------------------


class RebuildRequest(BaseModel):
    builder: str = Field("all", description="all | asset_port_vuln | identity | "
                                  "topology | alert_group | manual")


@router.post("/rebuild", summary="触发重建边（管理员）",
              dependencies=[Depends(require_role("admin", "operator"))])
async def post_rebuild(
    body: RebuildRequest,
    db: Session = Depends(get_db),
):
    """同步触发重建；异步可通过 task_execution 包装。"""
    stats: dict = {}
    try:
        if body.builder in ("all", "asset_port_vuln"):
            stats["asset_port_vuln"] = AssetPortVulnBuilder(db).rebuild_all()
        if body.builder in ("all", "identity"):
            stats["identity"] = IdentityGraphBuilder(db).rebuild_all()
        if body.builder in ("all", "topology"):
            stats["topology"] = TopologyBuilder(db).rebuild_all()
        if body.builder in ("all", "alert_group"):
            stats["alert_group"] = AlertGroupBuilder(db).rebuild_all()
        if body.builder in ("all", "manual"):
            stats["manual"] = ManualRelationBuilder(db).rebuild_all()
        # 清理过期边
        expired = delete_expired_edges(db)
        stats["expired_deleted"] = expired
        db.commit()
    except Exception as exc:
        logger.exception("rebuild failed")
        db.rollback()
        raise HTTPException(status_code=500, detail=f"重建失败: {exc.__class__.__name__}")

    return {"code": 200, "msg": "ok", "data": {"builder": body.builder, "stats": stats}}