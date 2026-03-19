"""
事件管理 API
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.models import Incident, AssetIncident
from app.schemas.incident import IncidentCreate, IncidentUpdate, IncidentResponse, IncidentListResponse
import uuid

router = APIRouter()


@router.get("/", response_model=IncidentListResponse)
async def list_incidents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    status: Optional[str] = None,
    severity: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取事件列表"""
    query = db.query(Incident)

    # 筛选条件
    if status:
        query = query.filter(Incident.status == status)
    if severity:
        query = query.filter(Incident.severity == severity)

    # 总数
    total = query.count()

    # 分页并按创建时间倒序
    incidents = query.order_by(Incident.created_at.desc()).offset(skip).limit(limit).all()

    return IncidentListResponse(
        items=[IncidentResponse.model_validate(incident) for incident in incidents],
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str, db: Session = Depends(get_db)):
    """获取事件详情"""
    try:
        incident_id_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的事件ID格式")

    incident = db.query(Incident).filter(Incident.id == incident_id_uuid).first()

    if not incident:
        raise HTTPException(status_code=404, detail="事件不存在")

    return IncidentResponse.model_validate(incident)


@router.post("/", response_model=IncidentResponse, status_code=201)
async def create_incident(incident_data: IncidentCreate, db: Session = Depends(get_db)):
    """创建事件"""
    # 创建事件
    incident_dict = incident_data.model_dump(exclude={"asset_ids"})
    incident = Incident(**incident_dict)
    db.add(incident)
    db.commit()
    db.refresh(incident)

    # 关联资产
    if incident_data.asset_ids:
        for asset_id in incident_data.asset_ids:
            try:
                asset_uuid = uuid.UUID(asset_id)
                asset_incident = AssetIncident(asset_id=asset_uuid, incident_id=incident.id)
                db.add(asset_incident)
            except ValueError:
                continue
        db.commit()
        db.refresh(incident)

    return IncidentResponse.model_validate(incident)


@router.put("/{incident_id}", response_model=IncidentResponse)
async def update_incident(incident_id: str, incident_data: IncidentUpdate, db: Session = Depends(get_db)):
    """更新事件"""
    try:
        incident_id_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的事件ID格式")

    incident = db.query(Incident).filter(Incident.id == incident_id_uuid).first()

    if not incident:
        raise HTTPException(status_code=404, detail="事件不存在")

    # 更新字段
    update_data = incident_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(incident, field, value)

    # 如果状态改为已解决，设置解决时间
    if incident.status == "resolved" and not incident.resolved_at:
        from datetime import datetime
        incident.resolved_at = datetime.utcnow()

    db.commit()
    db.refresh(incident)

    return IncidentResponse.model_validate(incident)


@router.post("/{incident_id}/timeline")
async def add_timeline_event(incident_id: str, event_data: dict, db: Session = Depends(get_db)):
    """添加事件时间线记录"""
    try:
        incident_id_uuid = uuid.UUID(incident_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的事件ID格式")

    incident = db.query(Incident).filter(Incident.id == incident_id_uuid).first()

    if not incident:
        raise HTTPException(status_code=404, detail="事件不存在")

    # TODO: 实现时间线记录功能
    # 需要创建 IncidentTimeline 模型

    return {"message": "时间线记录功能开发中", "incident_id": incident_id}
