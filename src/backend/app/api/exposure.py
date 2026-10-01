"""
暴露面归位 API（S2 / OH-4.2，2026-XX）

数据源：soc_maps_to（tplink-collector NAT 端口映射，OH-6.1b 同步）+
        soc_graph_edges maps_to 边（OH-3.4 入图）。

端点（前缀 /api/v1/exposure）：
  GET /lookup?wan_ip=x.y.x.z     外网 IP → 内网资产反查（S2 核心场景：
                                  攻击溯源/暴露面归位——"这个公网 IP 背后是谁"）
  GET /rules                     全量 NAT 规则（暴露面分析页数据源，
                                  支持 internal_ip 过滤）
  GET /assets/{asset_id}/mapping 资产暴露面映射（"这台资产哪些端口对外暴露"，
                                  挂在 assets 前缀下与资产详情页对齐）

envelope：{code, msg, data}（项目惯例，HTTP 200 + 业务码）。
权限：读端点，登录即可（对齐 graph.py 读端点）。

设计依据：docs/design/2026-09-30-资产管理AI能力建设方案.md §5.2（S2）
"""
from __future__ import annotations

import logging
from ipaddress import ip_address
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models import Asset
from app.models.nat_mapping import NatMapping

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exposure", tags=["exposure"])


def _mapping_row(m: NatMapping, asset: Asset | None) -> dict:
    """NatMapping 行 → API 字典（资产存在时附带归属信息）。"""
    return {
        "id": str(m.id),
        "source": m.source,
        "wan_ip": str(m.wan_ip) if m.wan_ip else None,
        "wan_if": m.wan_if,
        "protocol": m.protocol,
        "wan_port": m.wan_port,
        "internal_ip": str(m.internal_ip),
        "internal_port": m.internal_port,
        "rule_name": m.rule_name,
        "enabled": m.enabled,
        "last_seen_at": m.last_seen_at.isoformat() if m.last_seen_at else None,
        # 命中资产时附带（反查场景核心输出）
        "asset": (
            {
                "id": str(asset.id),
                "name": asset.name,
                "asset_ip": asset.asset_ip,
                "asset_type": asset.asset_type,
                "network_zone": asset.network_zone,
                "business_impact": asset.business_impact,
                "data_sensitivity": asset.data_sensitivity,
                "risk_score": asset.risk_score,
            }
            if asset
            else None
        ),
    }


def _assets_by_ip(db: Session, ips: list[str]) -> dict[str, Asset]:
    """internal_ip → Asset 映射（一次查询防 N+1）。"""
    if not ips:
        return {}
    rows = db.query(Asset).filter(Asset.asset_ip.in_(ips)).all()
    return {a.asset_ip: a for a in rows}


# ---------------------------------------------------------------------------
# ① GET /exposure/lookup —— 外网 IP → 内网资产反查（S2 核心）
# ---------------------------------------------------------------------------

@router.get("/lookup", summary="外网 IP→内网资产反查（S2 暴露面归位）")
async def exposure_lookup(
    wan_ip: str = Query(..., description="外网（WAN）IP"),
    enabled_only: bool = Query(True, description="只看启用规则"),
    db: Session = Depends(get_db),
    _auth=Depends(get_current_user),
):
    try:
        ip_address(wan_ip)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"wan_ip 不是合法 IP: {wan_ip!r}")

    q = db.query(NatMapping).filter(NatMapping.wan_ip == wan_ip)
    if enabled_only:
        q = q.filter(NatMapping.enabled.is_(True))
    rows = q.order_by(NatMapping.wan_port).all()

    assets = _assets_by_ip(db, [str(r.internal_ip) for r in rows])
    items = [_mapping_row(m, assets.get(str(m.internal_ip))) for m in rows]

    # 覆盖率口径：有映射 + 命中资产 / 有映射（诚实披露未纳管目标）
    located = sum(1 for x in items if x["asset"])
    return {
        "wan_ip": wan_ip,
        "total": len(items),
        "located": located,
        "unlocated": len(items) - located,
        "items": items,
    }


# ---------------------------------------------------------------------------
# ② GET /exposure/rules —— 全量 NAT 规则（暴露面分析页数据源）
# ---------------------------------------------------------------------------

@router.get("/rules", summary="NAT 端口映射规则列表")
async def exposure_rules(
    internal_ip: Optional[str] = Query(None, description="按内网目标 IP 过滤"),
    enabled_only: bool = Query(True, description="只看启用规则"),
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _auth=Depends(get_current_user),
):
    q = db.query(NatMapping)
    if internal_ip:
        try:
            ip_address(internal_ip)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"internal_ip 不是合法 IP")
        q = q.filter(NatMapping.internal_ip == internal_ip)
    if enabled_only:
        q = q.filter(NatMapping.enabled.is_(True))
    rows = q.order_by(NatMapping.wan_port).limit(limit).all()

    assets = _assets_by_ip(db, [str(r.internal_ip) for r in rows])
    items = [_mapping_row(m, assets.get(str(m.internal_ip))) for m in rows]

    # 汇总口径：多少个 WAN IP、多少资产被暴露、多少映射未命中资产
    wan_ips = {x["wan_ip"] for x in items if x["wan_ip"]}
    exposed_assets = {x["asset"]["id"] for x in items if x["asset"]}
    unlocated = sum(1 for x in items if not x["asset"])
    return {
        "total": len(items),
        "wan_ip_count": len(wan_ips),
        "exposed_asset_count": len(exposed_assets),
        "unlocated_count": unlocated,
        "items": items,
    }


# ---------------------------------------------------------------------------
# ③ GET /exposure/assets/{asset_id}/mapping —— 资产暴露面映射
# ---------------------------------------------------------------------------

@router.get("/assets/{asset_id}/mapping", summary="资产对外暴露面映射")
async def asset_exposure_mapping(
    asset_id: str,
    enabled_only: bool = Query(True),
    db: Session = Depends(get_db),
    _auth=Depends(get_current_user),
):
    from uuid import UUID as _UUID

    try:
        asset_uuid = _UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    asset = db.query(Asset).filter(Asset.id == asset_uuid).first()
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    q = db.query(NatMapping).filter(NatMapping.internal_ip == asset.asset_ip)
    if enabled_only:
        q = q.filter(NatMapping.enabled.is_(True))
    rows = q.order_by(NatMapping.wan_port).all()

    items = [
        {
            "id": str(m.id),
            "wan_ip": str(m.wan_ip) if m.wan_ip else None,
            "wan_if": m.wan_if,
            "protocol": m.protocol,
            "wan_port": m.wan_port,
            "internal_port": m.internal_port,
            "rule_name": m.rule_name,
            "enabled": m.enabled,
            "last_seen_at": m.last_seen_at.isoformat() if m.last_seen_at else None,
        }
        for m in rows
    ]
    return {
        "asset": {"id": str(asset.id), "name": asset.name, "asset_ip": asset.asset_ip},
        "exposed": len(items) > 0,
        "exposure_count": len(items),
        "items": items,
    }