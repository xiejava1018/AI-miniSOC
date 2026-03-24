"""
资产端口 API
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.models import AssetPort
from app.schemas.asset_port import AssetPortCreate, AssetPortUpdate, AssetPortResponse, AssetPortListResponse
import uuid

router = APIRouter()


@router.get("/{asset_id}/ports", response_model=AssetPortListResponse)
async def list_asset_ports(
    asset_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    protocol: Optional[str] = None,
    state: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取资产端口列表"""
    # 验证 asset_id 格式
    try:
        asset_id_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    query = db.query(AssetPort).filter(AssetPort.asset_id == asset_id_uuid)

    # 筛选条件
    if protocol:
        query = query.filter(AssetPort.protocol == protocol)
    if state:
        query = query.filter(AssetPort.state == state)

    # 总数
    total = query.count()

    # 分页并按端口号排序
    ports = query.order_by(AssetPort.port).offset(skip).limit(limit).all()

    # 手动转换为响应格式
    items = []
    for port in ports:
        items.append(AssetPortResponse(
            id=str(port.id),
            asset_id=str(port.asset_id) if port.asset_id else None,
            asset_ip=str(port.asset_ip),
            port=port.port,
            protocol=port.protocol,
            state=port.state,
            service=port.service,
            version=port.version,
            service_banner=port.service_banner,
            vulnerability=port.vulnerability,
            scan_time=port.scan_time,
            last_seen=port.last_seen,
            created_at=port.created_at,
        ))

    return AssetPortListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/ports/{port_id}", response_model=AssetPortResponse)
async def get_asset_port(port_id: str, db: Session = Depends(get_db)):
    """获取单个端口详情"""
    try:
        port_id_uuid = uuid.UUID(port_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的端口ID格式")

    port = db.query(AssetPort).filter(AssetPort.id == port_id_uuid).first()

    if not port:
        raise HTTPException(status_code=404, detail="端口不存在")

    return AssetPortResponse.model_validate(port)


@router.post("/{asset_id}/ports", response_model=AssetPortResponse, status_code=201)
async def create_asset_port(
    asset_id: str,
    port_data: AssetPortCreate,
    db: Session = Depends(get_db)
):
    """为资产创建端口"""
    # 验证 asset_id 格式
    try:
        asset_id_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    # 检查端口是否已存在
    existing_port = db.query(AssetPort).filter(
        AssetPort.asset_ip == port_data.asset_ip,
        AssetPort.port == port_data.port,
        AssetPort.protocol == port_data.protocol
    ).first()

    if existing_port:
        raise HTTPException(status_code=400, detail="该端口已存在")

    # 创建端口
    port = AssetPort(
        asset_id=asset_id_uuid,
        **port_data.model_dump()
    )
    db.add(port)
    db.commit()
    db.refresh(port)

    return AssetPortResponse.model_validate(port)


@router.put("/ports/{port_id}", response_model=AssetPortResponse)
async def update_asset_port(
    port_id: str,
    port_data: AssetPortUpdate,
    db: Session = Depends(get_db)
):
    """更新端口信息"""
    try:
        port_id_uuid = uuid.UUID(port_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的端口ID格式")

    port = db.query(AssetPort).filter(AssetPort.id == port_id_uuid).first()

    if not port:
        raise HTTPException(status_code=404, detail="端口不存在")

    # 更新字段
    update_data = port_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(port, field, value)

    db.commit()
    db.refresh(port)

    return AssetPortResponse.model_validate(port)


@router.delete("/ports/{port_id}")
async def delete_asset_port(port_id: str, db: Session = Depends(get_db)):
    """删除端口"""
    try:
        port_id_uuid = uuid.UUID(port_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的端口ID格式")

    port = db.query(AssetPort).filter(AssetPort.id == port_id_uuid).first()

    if not port:
        raise HTTPException(status_code=404, detail="端口不存在")

    db.delete(port)
    db.commit()

    return {"message": "端口删除成功"}


@router.delete("/{asset_id}/ports")
async def delete_all_asset_ports(asset_id: str, db: Session = Depends(get_db)):
    """删除资产的所有端口"""
    try:
        asset_id_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    # 删除该资产的所有端口
    deleted_count = db.query(AssetPort).filter(
        AssetPort.asset_id == asset_id_uuid
    ).delete()

    db.commit()

    return {
        "message": f"成功删除 {deleted_count} 个端口",
        "deleted_count": deleted_count
    }
