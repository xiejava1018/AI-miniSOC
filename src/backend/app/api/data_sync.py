"""
数据同步 API

接收 Collector 推送的采集数据，按 data_type 路由到对应 Handler 处理。
所有端点使用 API Key 认证（区别于用户 JWT）。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.api.deps import require_api_key, get_current_user
from app.core.database import get_db
from app.schemas.data_sync import DataSyncRequest, DataSyncResponse
from app.services.sync_handlers import SYNC_HANDLERS
from app.services.wazuh_agent_sync import WazuhAgentSyncService
from app.models.user import User

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


@router.post("/sync/wazuh-agents")
async def sync_wazuh_agents(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    同步 Wazuh Agents 到资产表

    从 Wazuh API 获取所有 agents 并同步到 soc_assets 表。
    支持手动触发或定时任务调用。

    需要 JWT 认证（用户登录）。
    """
    logger.info(f"用户 {current_user.username} 触发 Wazuh Agent 同步")

    # 使用后台任务执行同步
    def run_sync():
        try:
            sync_service = WazuhAgentSyncService(db)
            result = sync_service.sync_agents()
            logger.info(f"Wazuh Agent 后台同步完成: {result}")
        except Exception as e:
            logger.error(f"Wazuh Agent 后台同步失败: {e}")

    background_tasks.add_task(run_sync)

    return {
        "message": "Wazuh Agent 同步任务已启动",
        "status": "running"
    }


@router.get("/sync/wazuh-agents")
async def get_wazuh_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取 Wazuh Agents 列表（预览）

    返回从 Wazuh API 获取的 agents 列表，不执行同步。
    用于在同步前预览将要同步的数据。
    """
    try:
        from app.services.wazuh_client import wazuh_client

        agents = wazuh_client.get_agents()
        logger.info(f"获取到 {len(agents)} 个 Wazuh agents")

        # 简化返回数据
        simplified_agents = []
        for agent in agents:
            agent_info = agent.get("id", {})
            os_obj = agent.get("os", {})
            simplified_agents.append({
                "id": agent_info.get("id"),
                "name": agent_info.get("name"),
                "ip": agent_info.get("ip"),
                "status": agent.get("status"),
                "os": {
                    "name": os_obj.get("name"),
                    "version": os_obj.get("version")
                },
                "dateAdd": agent.get("dateAdd")
            })

        return {
            "total": len(simplified_agents),
            "agents": simplified_agents
        }

    except Exception as e:
        logger.error(f"获取 Wazuh Agents 失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取 Wazuh Agents 失败: {str(e)}")
