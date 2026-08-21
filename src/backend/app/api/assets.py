"""
资产管理 API
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.models import Asset
from app.models.asset_source import AssetSource
from app.schemas.asset import AssetCreate, AssetUpdate, AssetResponse, AssetListResponse
from app.services.asset_sync import AssetSyncService
from app.services.asset_summary import AssetSummaryService
from app.services.asset_overview import AssetOverviewService
from app.services.wazuh_inventory_service import WazuhInventoryService
import uuid

router = APIRouter()


@router.post("/sync/from-wazuh")
async def sync_assets_from_wazuh(db: Session = Depends(get_db)):
    """从 Wazuh 同步资产（返回任务ID）"""
    from app.services.asset_sync import AssetSyncService
    sync_service = AssetSyncService(db)
    try:
        task = sync_service.sync_from_wazuh_with_tracking("manual")
        return {
            "message": "同步任务已创建",
            "task_id": str(task.id),
            "status": task.status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"资产同步失败: {str(e)}")


@router.get("/", response_model=AssetListResponse)
@router.get("", response_model=AssetListResponse)
async def list_assets(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    asset_ip: Optional[str] = None,
    name: Optional[str] = None,
    asset_type: Optional[str] = None,
    criticality: Optional[str] = None,
    asset_status: Optional[str] = None,
    network_zone: Optional[str] = None,
    data_source: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取资产列表"""
    query = db.query(Asset)

    # 筛选条件
    if asset_ip:
        query = query.filter(Asset.asset_ip.contains(asset_ip))
    if name:
        query = query.filter(Asset.name.contains(name))
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)
    if criticality:
        query = query.filter(Asset.criticality == criticality)
    if asset_status:
        query = query.filter(Asset.asset_status == asset_status)
    if network_zone:
        query = query.filter(Asset.network_zone == network_zone)
    if data_source:
        query = query.filter(
            Asset.id.in_(
                db.query(AssetSource.asset_id).filter(
                    AssetSource.source == data_source
                )
            )
        )

    # 总数
    total = query.count()

    # 分页
    assets = query.offset(skip).limit(limit).all()

    # 手动转换为响应格式
    items = []
    for asset in assets:
        items.append(AssetResponse(
            id=str(asset.id),
            name=asset.name,
            asset_ip=asset.asset_ip,
            asset_type=asset.asset_type,
            criticality=asset.criticality,
            owner=asset.owner,
            business_unit=asset.business_unit,
            asset_description=asset.asset_description,
            mac_address=str(asset.mac_address) if asset.mac_address else None,
            wazuh_agent_id=asset.wazuh_agent_id,
            asset_status=asset.asset_status,
            network_segment=asset.network_segment,
            network_zone=asset.network_zone,
            data_source=asset.data_source,
            os_name=asset.os_name,
            os_version=asset.os_version,
            created_at=asset.created_at,
            updated_at=asset.updated_at,
            status_updated_at=asset.status_updated_at,
            parent_id=asset.parent_id,
            data_classification=asset.data_classification,
            owner_contact=asset.owner_contact,
            risk_score=asset.risk_score,
            risk_scored_at=asset.risk_scored_at,
            purchase_date=asset.purchase_date,
            warranty_end=asset.warranty_end,
            expected_eol=asset.expected_eol,
            expected_eol_source=asset.expected_eol_source,
        ))

    return AssetListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/{asset_id}/sources")
@router.get("/{asset_id}/sources/")
async def get_asset_sources(asset_id: str, db: Session = Depends(get_db)):
    """获取资产的所有数据来源"""
    try:
        asset_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    asset = db.query(Asset).filter(Asset.id == asset_uuid).first()
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    sources = db.query(AssetSource).filter(
        AssetSource.asset_id == asset_uuid
    ).order_by(AssetSource.last_seen_at.desc()).all()

    return [
        {
            "source": s.source,
            "source_id": s.source_id,
            "source_status": s.source_status,
            "last_seen_at": s.last_seen_at.isoformat() if s.last_seen_at else None,
            "source_metadata": s.source_metadata,
        }
        for s in sources
    ]


@router.get("/{asset_id}/applications")
@router.get("/{asset_id}/applications/")
async def get_asset_applications(
    asset_id: str,
    search: Optional[str] = Query(None, description="包名模糊搜索"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db)
):
    """
    获取资产已安装应用清单（M3：OpenSearch wazuh-states-inventory-packages 直查）

    - 资产无 wazuh_agent_id → not_applicable（前端显专用空态）
    - agent 未开启包清点/索引无数据 → 空列表
    - OpenSearch 不可用 → 503 业务码（与告警 Tab 同降级语义）
    """
    try:
        asset_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    asset = db.query(Asset).filter(Asset.id == asset_uuid).first()
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    if not asset.wazuh_agent_id:
        return {"not_applicable": True, "items": [], "total": 0,
                "reason": "该资产无 Wazuh Agent，应用清单数据不适用"}

    service = WazuhInventoryService()
    try:
        return service.get_applications(asset.wazuh_agent_id, search=search, skip=skip, limit=limit)
    except Exception:
        raise HTTPException(status_code=503, detail="应用清单数据源(OpenSearch)暂不可用")
    finally:
        service.close()


@router.get("/{asset_id}/wazuh-ports")
@router.get("/{asset_id}/wazuh-ports/")
async def get_asset_wazuh_ports(
    asset_id: str,
    db: Session = Depends(get_db)
):
    """
    获取资产 Wazuh 实时监听端口（M4：OpenSearch states-inventory-ports，带进程信息）

    与本地 soc_asset_ports（手动/nmap）双源合并展示的 Wazuh 侧数据源。
    """
    try:
        asset_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    asset = db.query(Asset).filter(Asset.id == asset_uuid).first()
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    if not asset.wazuh_agent_id:
        return {"not_applicable": True, "items": [],
                "reason": "该资产无 Wazuh Agent，实时端口数据不适用"}

    service = WazuhInventoryService()
    try:
        return {"items": service.get_ports(asset.wazuh_agent_id)}
    except Exception:
        raise HTTPException(status_code=503, detail="端口数据源(OpenSearch)暂不可用")
    finally:
        service.close()


@router.get("/overview")
@router.get("/overview/")
async def get_asset_overview(db: Session = Depends(get_db)):
    """
    获取资产概览聚合数据(SOC 风险全貌)

    一次性返回 4 个 KPI + 3 张分布图 + 24h 告警趋势 + 2 张 Top 表,
    供「资产概览」页 + Dashboard console 入口卡使用。

    任意子步骤失败不影响其他字段,失败字段降级为 0 / 空。
    """
    service = AssetOverviewService(db)
    return service.build_overview()


@router.get("/{asset_id}", response_model=AssetResponse)
@router.get("/{asset_id}/", response_model=AssetResponse)
async def get_asset(asset_id: str, db: Session = Depends(get_db)):
    """获取单个资产详情"""
    try:
        asset_id_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    asset = db.query(Asset).filter(Asset.id == asset_id_uuid).first()

    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    return AssetResponse.model_validate(asset)


@router.get("/{asset_id}/summary")
@router.get("/{asset_id}/summary/")
async def get_asset_summary(asset_id: str, db: Session = Depends(get_db)):
    """
    获取资产安全摘要(详情页 v2)

    聚合该资产所需的 6+ 个 MetricCard 数据,具体字段见
    docs/design/2026-06-03-asset-detail-v2-design.md §7.1
    Wazuh 相关字段(漏洞/应用/SCA)在 Phase 2 接入后填充。
    """
    try:
        uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    asset = db.query(Asset).filter(Asset.id == uuid.UUID(asset_id)).first()
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    summary_service = AssetSummaryService(db)
    return summary_service.build_summary(asset_id)


@router.post("/", response_model=AssetResponse, status_code=201)
@router.post("", response_model=AssetResponse, status_code=201)
async def create_asset(asset_data: AssetCreate, db: Session = Depends(get_db)):
    """创建资产"""
    from app.services.audit_log_service import AuditLogService
    from app.core.auth import get_current_user
    from fastapi import Request

    # 可选：检查IP是否已存在，如果存在则返回已存在的资产（而不是阻止创建）
    # 这里我们允许创建重复IP的资产，因为不同资产可能使用相同IP（比如内网IP复用）
    # 如果需要严格唯一性，可以取消注释以下代码：
    # existing = db.query(Asset).filter(Asset.asset_ip == asset_data.asset_ip).first()
    # if existing:
    #     raise HTTPException(status_code=400, detail="该IP地址已存在")

    # 创建资产
    asset = Asset(**asset_data.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)

    # 记录审计日志（在后台任务中，避免延迟响应）
    audit_service = AuditLogService(db)
    audit_service.create_audit_log(
        user_id=None,  # 从上下文获取
        username="system",  # 临时使用
        action="CREATE",
        resource_type="asset",
        resource_id=None,  # 资产ID是UUID，resource_id字段是BigInteger，不传
        resource_name=asset.name or asset.asset_ip,
        new_values={"asset_ip": asset.asset_ip, "asset_type": asset.asset_type},
        status="success"
    )

    return AssetResponse.model_validate(asset)


@router.put("/{asset_id}", response_model=AssetResponse)
@router.put("/{asset_id}/", response_model=AssetResponse)
async def update_asset(asset_id: str, asset_data: AssetUpdate, db: Session = Depends(get_db)):
    """更新资产"""
    from app.services.audit_log_service import AuditLogService

    try:
        asset_id_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    asset = db.query(Asset).filter(Asset.id == asset_id_uuid).first()

    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    # 保存旧值用于审计日志
    old_values = {}
    update_data = asset_data.model_dump(exclude_unset=True)

    for field in update_data.keys():
        old_value = getattr(asset, field, None)
        if old_value is not None:
            old_values[field] = str(old_value) if not isinstance(old_value, (int, float, str, bool)) else old_value

    # 更新字段
    for field, value in update_data.items():
        setattr(asset, field, value)

    db.commit()
    db.refresh(asset)

    # 记录审计日志
    if update_data:
        audit_service = AuditLogService(db)
        audit_service.create_audit_log(
            user_id=None,
            username="system",
            action="UPDATE",
            resource_type="asset",
            resource_id=None,  # 资产ID是UUID，resource_id字段是BigInteger，不传
            resource_name=asset.name or asset.asset_ip,
            old_values=old_values if old_values else None,
            new_values=update_data,
            status="success"
        )

    return AssetResponse.model_validate(asset)


@router.delete("/{asset_id}")
@router.delete("/{asset_id}/")
async def delete_asset(asset_id: str, db: Session = Depends(get_db)):
    """删除资产"""
    from app.services.audit_log_service import AuditLogService
    import json

    try:
        asset_id_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    asset = db.query(Asset).filter(Asset.id == asset_id_uuid).first()

    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    # 保存资产信息用于审计日志
    asset_info = {
        "id": str(asset.id),
        "name": asset.name,
        "asset_ip": asset.asset_ip,
        "asset_type": asset.asset_type
    }

    db.delete(asset)
    db.commit()

    # 记录审计日志
    audit_service = AuditLogService(db)
    audit_service.create_audit_log(
        user_id=None,
        username="system",
        action="DELETE",
        resource_type="asset",
        resource_id=None,  # 资产ID是UUID，resource_id字段是BigInteger，不传
        resource_name=asset_info.get("name") or asset_info.get("asset_ip"),
        old_values=asset_info,
        status="success"
    )

    return {"message": "资产删除成功"}
