"""配置 Schema API

供前端配置中心动态渲染表单（Schema-driven Form）。
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import get_db
from app.models.config_schema import ConfigSchema
from app.schemas.config_schema import (
    ConfigSchemaGroup,
    ConfigSchemaListResponse,
    ConfigSchemaResponse,
)
from app.schemas.user import UserResponse as UserResponseSchema

router = APIRouter()


@router.get("", response_model=ConfigSchemaListResponse)
async def list_config_schemas(
    category: Optional[str] = Query(None, description="按分类过滤；不传则返回全部"),
    current_user: UserResponseSchema = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(ConfigSchema)
    if category:
        q = q.filter(ConfigSchema.category == category)
    items = q.order_by(ConfigSchema.category, ConfigSchema.sort_order, ConfigSchema.key).all()

    # 按 category 分组
    groups_map: dict[str, list[ConfigSchemaResponse]] = {}
    for it in items:
        groups_map.setdefault(it.category, []).append(
            ConfigSchemaResponse.model_validate(it)
        )
    groups = [
        ConfigSchemaGroup(category=k, count=len(v), items=v)
        for k, v in sorted(groups_map.items())
    ]
    return ConfigSchemaListResponse(
        items=[ConfigSchemaResponse.model_validate(i) for i in items],
        groups=groups,
    )