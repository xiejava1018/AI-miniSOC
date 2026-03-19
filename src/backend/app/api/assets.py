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
    """从 Wazuh 同步资产"""
    sync_service = AssetSyncService(db)
    try:
        result = sync_service.sync_from_wazuh()
        return {
            "message": "资产同步完成",
            "status": "completed",
            "result": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"资产同步失败: {str(e)}")


@router.get("/", response_model=AssetListResponse)
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
async def create_asset(asset_data: AssetCreate, db: Session = Depends(get_db)):
    """创建资产"""
    # 检查IP是否已存在
    existing = db.query(Asset).filter(Asset.asset_ip == asset_data.asset_ip).first()
    if existing:
        raise HTTPException(status_code=400, detail="该IP地址已存在")

    # 创建资产
    asset = Asset(**asset_data.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)

    return AssetResponse.model_validate(asset)


@router.put("/{asset_id}", response_model=AssetResponse)
async def update_asset(asset_id: str, asset_data: AssetUpdate, db: Session = Depends(get_db)):
    """更新资产"""
    try:
        asset_id_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    asset = db.query(Asset).filter(Asset.id == asset_id_uuid).first()

    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    # 更新字段
    update_data = asset_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(asset, field, value)

    db.commit()
    db.refresh(asset)

    return AssetResponse.model_validate(asset)


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str, db: Session = Depends(get_db)):
    """删除资产"""
    try:
        asset_id_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    asset = db.query(Asset).filter(Asset.id == asset_id_uuid).first()

    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    db.delete(asset)
    db.commit()

    return {"message": "资产删除成功"}
