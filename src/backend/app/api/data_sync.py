"""
数据同步 API

接收 Collector 推送的采集数据，按 data_type 路由到对应 Handler 处理。
所有端点使用 API Key 认证（区别于用户 JWT）。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_api_key
from app.core.database import get_db
from app.schemas.data_sync import DataSyncRequest, DataSyncResponse
from app.services.sync_handlers import SYNC_HANDLERS

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sync", response_model=DataSyncResponse)
async def sync_data(
    request: DataSyncRequest,
    db: Session = Depends(get_db),
    _auth: str = Depends(require_api_key),
):
    """
    通用数据同步接口 — 由 Collector 调用

    根据 data_type 路由到对应的 Handler 处理：
    - asset: 资产同步（去重、增量更新、变更记录）
    - vulnerability: 漏洞同步（Phase 2）
    - baseline: 基线同步（Phase 3）
    - port: 端口同步（Phase 4）
    """
    handler = SYNC_HANDLERS.get(request.data_type)
    if not handler:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的数据类型: {request.data_type}，"
                   f"当前支持: {', '.join(SYNC_HANDLERS.keys())}",
        )

    logger.info(
        f"收到数据同步请求: source={request.source}, "
        f"type={request.data_type}, items={len(request.items)}"
    )

    try:
        result = handler.handle(request.source, request.items, db)
    except Exception as e:
        logger.error(f"数据同步处理失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"数据同步失败: {str(e)}")

    return DataSyncResponse(
        message="同步完成",
        data_type=request.data_type,
        source=request.source,
        **result,
    )
