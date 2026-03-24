"""
资产-事件关联 API
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional, List
from app.core.database import get_db
from app.models import Asset, Incident, AssetIncident
from app.schemas.asset import AssetResponse
from app.schemas.incident import IncidentResponse
import uuid

router = APIRouter()


@router.get("/{asset_id}/incidents", response_model=List[IncidentResponse])
async def get_asset_incidents(
    asset_id: str,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取资产关联的所有事件"""
    try:
        asset_id_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    # 验证资产存在
    asset = db.query(Asset).filter(Asset.id == asset_id_uuid).first()
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    # 查询关联的事件
    query = db.query(Incident).join(AssetIncident).filter(
        AssetIncident.asset_id == asset_id_uuid
    )

    if status:
        query = query.filter(Incident.status == status)
    if severity:
        query = query.filter(Incident.severity == severity)

    incidents = query.order_by(Incident.created_at.desc()).all()

    return [IncidentResponse.model_validate(inc) for inc in incidents]


@router.post("/{asset_id}/incidents/{incident_id}")
async def link_asset_incident(
    asset_id: str,
    incident_id: str,
    db: Session = Depends(get_db)
):
    """关联资产和事件"""
    try:
        asset_id_uuid = uuid.UUID(asset_id)
        incident_id_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的ID格式")

    # 验证资产存在
    asset = db.query(Asset).filter(Asset.id == asset_id_uuid).first()
    if not asset:
        raise HTTPException(status_code=404, detail="资产不存在")

    # 验证事件存在
    incident = db.query(Incident).filter(Incident.id == incident_id_uuid).first()
    if not incident:
        raise HTTPException(status_code=404, detail="事件不存在")

    # 检查是否已关联
    existing = db.query(AssetIncident).filter(
        AssetIncident.asset_id == asset_id_uuid,
        AssetIncident.incident_id == incident_id_uuid
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="该资产和事件已经关联")

    # 创建关联
    link = AssetIncident(asset_id=asset_id_uuid, incident_id=incident_id_uuid)
    db.add(link)
    db.commit()

    return {
        "message": "关联成功",
        "asset_id": str(asset_id_uuid),
        "incident_id": str(incident_id_uuid)
    }


@router.delete("/{asset_id}/incidents/{incident_id}")
async def unlink_asset_incident(
    asset_id: str,
    incident_id: str,
    db: Session = Depends(get_db)
):
    """取消资产和事件的关联"""
    try:
        asset_id_uuid = uuid.UUID(asset_id)
        incident_id_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的ID格式")

    # 查找关联
    link = db.query(AssetIncident).filter(
        AssetIncident.asset_id == asset_id_uuid,
        AssetIncident.incident_id == incident_id_uuid
    ).first()

    if not link:
        raise HTTPException(status_code=404, detail="关联关系不存在")

    db.delete(link)
    db.commit()

    return {"message": "取消关联成功"}
