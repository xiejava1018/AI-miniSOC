"""
资产管理 API
"""

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.models import Asset
from app.schemas.asset import AssetCreate, AssetUpdate, AssetResponse, AssetListResponse
from app.services.asset_sync import AssetSyncService
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
    asset_type: Optional[str] = None,
    criticality: Optional[str] = None,
    asset_status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取资产列表"""
    query = db.query(Asset)

    # 筛选条件
    if asset_type:
        query = query.filter(Asset.asset_type == asset_type)
    if criticality:
        query = query.filter(Asset.criticality == criticality)
    if asset_status:
        query = query.filter(Asset.asset_status == asset_status)

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
            created_at=asset.created_at,
            updated_at=asset.updated_at,
            status_updated_at=asset.status_updated_at,
            parent_id=asset.parent_id,
        ))

    return AssetListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit
    )


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
