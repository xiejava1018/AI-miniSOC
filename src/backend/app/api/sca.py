"""
SCA基线核查同步 API
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any
from app.core.database import get_db
from app.services.wazuh_sca_sync_v2 import WazuhSCASyncServiceV2
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/sync/all")
async def sync_all_sca_checks(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    同步所有活跃agent的SCA检查数据

    Returns:
        同步结果统计
    """
    try:
        logger.info("开始同步所有SCA检查数据...")

        stats = WazuhSCASyncServiceV2.sync_all_sca_checks(db=db)

        logger.info(f"SCA同步完成: {stats}")

        return {
            "success": True,
            "message": "SCA数据同步完成",
            "data": stats
        }

    except Exception as e:
        logger.error(f"SCA同步失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"SCA同步失败: {str(e)}"
        )


@router.post("/sync/agent/{agent_id}")
async def sync_agent_sca_checks(
    agent_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    同步指定agent的SCA检查数据

    Args:
        agent_id: Wazuh Agent ID

    Returns:
        同步结果统计
    """
    try:
        logger.info(f"开始同步Agent {agent_id}的SCA检查数据...")

        # 获取agent信息
        from app.services.wazuh_client import wazuh_client
        agents = wazuh_client.get_agents()
        agent = next((a for a in agents if a.get("id") == agent_id), None)

        if not agent:
            raise HTTPException(
                status_code=404,
                detail=f"Agent {agent_id} 不存在"
            )

        stats = WazuhSCASyncServiceV2.sync_agent_sca_checks(
            db=db,
            agent_id=agent_id,
            agent_name=agent.get("name"),
            agent_ip=agent.get("ip")
        )

        logger.info(f"Agent {agent_id} SCA同步完成: {stats}")

        return {
            "success": True,
            "message": f"Agent {agent_id} SCA数据同步完成",
            "data": stats
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Agent {agent_id} SCA同步失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Agent {agent_id} SCA同步失败: {str(e)}"
        )


@router.get("/stats/overview")
async def get_sca_statistics(
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取SCA检查统计数据

    Returns:
        SCA统计数据
    """
    try:
        stats = WazuhSCASyncServiceV2.get_sca_statistics(db=db)

        return {
            "success": True,
            "data": stats
        }

    except Exception as e:
        logger.error(f"获取SCA统计失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"获取SCA统计失败: {str(e)}"
        )


@router.get("/checks")
async def list_sca_checks(
    skip: int = 0,
    limit: int = 100,
    policy_id: str = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取SCA检查项列表

    Args:
        skip: 跳过数量
        limit: 返回数量限制
        policy_id: 策略ID过滤

    Returns:
        检查项列表
    """
    try:
        from app.models.sca import ScaCheck
        from sqlalchemy import func

        query = db.query(ScaCheck)

        if policy_id:
            query = query.filter(ScaCheck.policy_id == policy_id)

        total = query.count()
        checks = query.offset(skip).limit(limit).all()

        return {
            "success": True,
            "data": {
                "total": total,
                "items": [
                    {
                        "id": str(check.id),
                        "check_id": check.check_id,
                        "policy_id": check.policy_id,
                        "title": check.title,
                        "description": check.description,
                        "rationale": check.rationale,
                        "remediation": check.remediation
                    }
                    for check in checks
                ]
            }
        }

    except Exception as e:
        logger.error(f"获取SCA检查项列表失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"获取SCA检查项列表失败: {str(e)}"
        )


@router.get("/results")
async def list_asset_sca_results(
    skip: int = 0,
    limit: int = 100,
    asset_id: str = None,
    result: str = None,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取资产SCA检查结果列表

    Args:
        skip: 跳过数量
        limit: 返回数量限制
        asset_id: 资产ID过滤
        result: 结果过滤 (passed/failed/not applicable)

    Returns:
        检查结果列表
    """
    try:
        from app.models.sca import AssetScaCheck, ScaCheck
        from app.models.asset import Asset
        from sqlalchemy import func

        query = db.query(
            AssetScaCheck,
            ScaCheck,
            Asset
        ).join(
            ScaCheck, AssetScaCheck.sca_check_id == ScaCheck.id
        ).join(
            Asset, AssetScaCheck.asset_id == Asset.id
        )

        if asset_id:
            query = query.filter(AssetScaCheck.asset_id == asset_id)

        if result:
            query = query.filter(AssetScaCheck.result == result)

        total = query.count()
        results = query.offset(skip).limit(limit).all()

        return {
            "success": True,
            "data": {
                "total": total,
                "items": [
                    {
                        "id": str(asset_sca.id),
                        "asset_id": str(asset_sca.asset_id),
                        "asset_name": asset.name,
                        "sca_check_id": str(asset_sca.sca_check_id),
                        "check_id": sca_check.check_id,
                        "policy_id": sca_check.policy_id,
                        "title": sca_check.title,
                        "result": asset_sca.result,
                        "reason": asset_sca.reason,
                        "status": asset_sca.status,
                        "last_scan_time": asset_sca.last_scan_time.isoformat() if asset_sca.last_scan_time else None
                    }
                    for asset_sca, sca_check, asset in results
                ]
            }
        }

    except Exception as e:
        logger.error(f"获取资产SCA检查结果失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"获取资产SCA检查结果失败: {str(e)}"
        )
