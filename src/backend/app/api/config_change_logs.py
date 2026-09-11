"""配置变更审计 API

仅 admin 可读（与设计文档 §5.5 一致）。
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.core.permissions import require_admin
from app.schemas.config_change_log import (
    ConfigChangeLogListResponse,
    ConfigChangeLogResponse,
)
from app.schemas.user import UserResponse as UserResponseSchema
from app.services.config_change_log_service import ConfigChangeLogService

router = APIRouter()


@router.get("", response_model=ConfigChangeLogListResponse)
async def list_config_change_logs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    target_type: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    current_user: UserResponseSchema = Depends(require_admin()),
    db: Session = Depends(get_db),
):
    svc = ConfigChangeLogService(db)
    items, total = svc.list(
        page=page,
        page_size=page_size,
        target_type=target_type,
        action=action,
        search=search,
    )
    return ConfigChangeLogListResponse(
        total=total,
        items=[ConfigChangeLogResponse.model_validate(i) for i in items],
        page=page,
        page_size=page_size,
    )