"""数据源管理 API

设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §5.5 / §5.6

权限矩阵：
  GET  → 登录用户
  POST/PUT/PATCH/DELETE/测试连接 → 仅 admin
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.permissions import require_admin
from app.models.user import User
from app.schemas.data_source import (
    DataSourceCreate,
    DataSourceListResponse,
    DataSourceResponse,
    DataSourceTypesResponse,
    DataSourceTypeItem,
    DataSourceUpdate,
    EnabledToggleRequest,
    ResolveStatusItem,
    ResolveStatusResponse,
    SOURCE_TYPES,
    TestConnectionRequest,
    TestConnectionResponse,
)
from app.schemas.user import UserResponse as UserResponseSchema
from app.services.config_test_service import ConfigTestService
from app.services.data_source_resolver import data_source_resolver
from app.services.data_source_service import DataSourceService, DataSourceServiceError, to_response

router = APIRouter()


# ---------------------------------------------------------------------------
# /types 必须在 /{id} 之前注册，否则会被 catch-all 抢匹配
# ---------------------------------------------------------------------------
@router.get("/types", response_model=DataSourceTypesResponse)
async def get_data_source_types(
    current_user: UserResponseSchema = Depends(get_current_user),
):
    return DataSourceTypesResponse(
        items=[DataSourceTypeItem(**t) for t in SOURCE_TYPES]
    )


@router.get("/resolve-status", response_model=ResolveStatusResponse)
async def get_resolve_status(
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    status_map = data_source_resolver.resolve_status(db)
    items = []
    for t, rc in status_map.items():
        # 找一条 DB 行用于 enabled / is_default 标记
        from app.models.data_source import DataSource

        ds = (
            db.query(DataSource)
            .filter(
                DataSource.source_type == t,
                DataSource.source_code == rc.source_code,
            )
            .first()
            if rc.source_code
            else None
        )
        items.append(
            ResolveStatusItem(
                source_type=t,
                origin=rc.origin,
                source_code=rc.source_code,
                enabled=bool(ds and ds.enabled),
                is_default=bool(ds and ds.is_default),
            )
        )
    return ResolveStatusResponse(items=items)


@router.get("", response_model=DataSourceListResponse)
async def list_data_sources(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source_type: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = DataSourceService(db)
    items, total = svc.list(
        page=page, page_size=page_size, source_type=source_type, search=search
    )
    return DataSourceListResponse(
        total=total,
        items=[DataSourceResponse.model_validate(to_response(i)) for i in items],
        page=page,
        page_size=page_size,
    )


@router.get("/{source_id}", response_model=DataSourceResponse)
async def get_data_source(
    source_id: int,
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    svc = DataSourceService(db)
    try:
        ds = svc.get_by_id(source_id)
    except DataSourceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return DataSourceResponse.model_validate(to_response(ds))


@router.post("", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_data_source(
    request: Request,
    data: DataSourceCreate,
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    svc = DataSourceService(db)
    try:
        ip = request.client.host if request.client else None
        ds = svc.create(data, operator_id=current_user.id, operator_ip=ip)
    except DataSourceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return DataSourceResponse.model_validate(to_response(ds))


@router.put("/{source_id}", response_model=DataSourceResponse)
async def update_data_source(
    request: Request,
    source_id: int,
    data: DataSourceUpdate,
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    svc = DataSourceService(db)
    try:
        ip = request.client.host if request.client else None
        ds = svc.update(source_id, data, operator_id=current_user.id, operator_ip=ip)
    except DataSourceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return DataSourceResponse.model_validate(to_response(ds))


@router.delete("/{source_id}")
async def delete_data_source(
    request: Request,
    source_id: int,
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    svc = DataSourceService(db)
    try:
        ip = request.client.host if request.client else None
        svc.delete(source_id, operator_id=current_user.id, operator_ip=ip)
    except DataSourceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return {"success": True}


@router.patch("/{source_id}/enabled", response_model=DataSourceResponse)
async def toggle_data_source_enabled(
    request: Request,
    source_id: int,
    body: EnabledToggleRequest,
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    svc = DataSourceService(db)
    try:
        ip = request.client.host if request.client else None
        ds = svc.set_enabled(
            source_id, body.enabled, operator_id=current_user.id, operator_ip=ip
        )
    except DataSourceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return DataSourceResponse.model_validate(to_response(ds))


@router.post("/{source_id}/set-default", response_model=DataSourceResponse)
async def set_default_data_source(
    request: Request,
    source_id: int,
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    svc = DataSourceService(db)
    try:
        ip = request.client.host if request.client else None
        ds = svc.set_default(source_id, operator_id=current_user.id, operator_ip=ip)
    except DataSourceServiceError as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    return DataSourceResponse.model_validate(to_response(ds))


@router.post("/test", response_model=TestConnectionResponse)
async def test_data_source(
    request: Request,
    payload: TestConnectionRequest,
    current_user: User = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    """测试连接。"""
    svc = DataSourceService(db)
    test_svc = ConfigTestService(db)

    if payload.id is not None:
        try:
            ds = svc.get_by_id(payload.id)
        except DataSourceServiceError as e:
            raise HTTPException(status_code=e.status_code, detail=e.message)
        from app.services.encryption_service import encryption_service

        secret = encryption_service.decrypt_if_needed(ds.auth_secret) if ds.auth_secret else None
        result = test_svc.test(
            source_type=ds.source_type,
            endpoint=ds.endpoint,
            auth_type=ds.auth_type,
            auth_username=ds.auth_username,
            auth_secret=secret,
            verify_ssl=ds.verify_ssl,
            timeout_seconds=ds.timeout_seconds,
            config_json=ds.config_json,
        )
    else:
        draft = payload.draft
        if draft is None:
            raise HTTPException(status_code=400, detail="id 与 draft 必填其一")
        result = test_svc.test(
            source_type=draft.source_type,
            endpoint=draft.endpoint,
            auth_type=draft.auth_type,
            auth_username=draft.auth_username,
            auth_secret=draft.auth_secret,
            verify_ssl=draft.verify_ssl,
            timeout_seconds=draft.timeout_seconds,
            config_json=draft.config_json,
        )

    # 若指定了 id，把结果写回 + 写审计
    if payload.id is not None:
        svc.record_test_result(
            payload.id,
            ok=result.ok,
            message=result.message,
        )

    return result