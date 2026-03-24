"""
资产标签 API
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.core.database import get_db
from app.models import AssetTag
from app.schemas.asset_tag import (
    AssetTagCreate,
    AssetTagUpdate,
    AssetTagResponse,
    AssetTagListResponse,
    COMMON_TAG_KEYS
)
import uuid

router = APIRouter()


@router.get("/{asset_id}/tags", response_model=AssetTagListResponse)
async def list_asset_tags(
    asset_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    tag_key: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """获取资产标签列表"""
    try:
        asset_id_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    query = db.query(AssetTag).filter(AssetTag.asset_id == asset_id_uuid)

    if tag_key:
        query = query.filter(AssetTag.tag_key == tag_key)

    total = query.count()
    tags = query.order_by(AssetTag.tag_key).offset(skip).limit(limit).all()

    items = []
    for tag in tags:
        items.append(AssetTagResponse(
            id=str(tag.id),
            asset_id=str(tag.asset_id),
            tag_key=tag.tag_key,
            tag_value=tag.tag_value,
            created_at=tag.created_at,
        ))

    return AssetTagListResponse(
        items=items,
        total=total,
        skip=skip,
        limit=limit
    )


@router.get("/tags/{tag_id}", response_model=AssetTagResponse)
async def get_asset_tag(tag_id: str, db: Session = Depends(get_db)):
    """获取单个标签详情"""
    try:
        tag_id_uuid = uuid.UUID(tag_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的标签ID格式")

    tag = db.query(AssetTag).filter(AssetTag.id == tag_id_uuid).first()

    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")

    return AssetTagResponse.model_validate(tag)


@router.post("/{asset_id}/tags", response_model=AssetTagResponse, status_code=201)
async def create_asset_tag(
    asset_id: str,
    tag_data: AssetTagCreate,
    db: Session = Depends(get_db)
):
    """为资产创建标签"""
    try:
        asset_id_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    # 检查标签是否已存在（同一资产同一标签键只能有一个值）
    existing_tag = db.query(AssetTag).filter(
        AssetTag.asset_id == asset_id_uuid,
        AssetTag.tag_key == tag_data.tag_key
    ).first()

    if existing_tag:
        raise HTTPException(
            status_code=400,
            detail=f"该资产已存在标签键 '{tag_data.tag_key}'，请使用更新接口修改值"
        )

    tag = AssetTag(
        asset_id=asset_id_uuid,
        **tag_data.model_dump()
    )
    db.add(tag)
    db.commit()
    db.refresh(tag)

    return AssetTagResponse.model_validate(tag)


@router.put("/tags/{tag_id}", response_model=AssetTagResponse)
async def update_asset_tag(
    tag_id: str,
    tag_data: AssetTagUpdate,
    db: Session = Depends(get_db)
):
    """更新标签值"""
    try:
        tag_id_uuid = uuid.UUID(tag_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的标签ID格式")

    tag = db.query(AssetTag).filter(AssetTag.id == tag_id_uuid).first()

    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")

    tag.tag_value = tag_data.tag_value
    db.commit()
    db.refresh(tag)

    return AssetTagResponse.model_validate(tag)


@router.delete("/tags/{tag_id}")
async def delete_asset_tag(tag_id: str, db: Session = Depends(get_db)):
    """删除标签"""
    try:
        tag_id_uuid = uuid.UUID(tag_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的标签ID格式")

    tag = db.query(AssetTag).filter(AssetTag.id == tag_id_uuid).first()

    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")

    db.delete(tag)
    db.commit()

    return {"message": "标签删除成功"}


@router.delete("/{asset_id}/tags")
async def delete_all_asset_tags(asset_id: str, db: Session = Depends(get_db)):
    """删除资产的所有标签"""
    try:
        asset_id_uuid = uuid.UUID(asset_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的资产ID格式")

    deleted_count = db.query(AssetTag).filter(
        AssetTag.asset_id == asset_id_uuid
    ).delete()

    db.commit()

    return {
        "message": f"成功删除 {deleted_count} 个标签",
        "deleted_count": deleted_count
    }


@router.get("/tags/common-keys")
async def get_common_tag_keys():
    """获取常用标签键及其建议值"""
    return {
        "common_tag_keys": COMMON_TAG_KEYS
    }
