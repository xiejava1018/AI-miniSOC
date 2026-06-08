"""
告警管理 API (Wazuh集成)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
from app.core.database import get_db
from app.services.alert_query import AlertQueryService

router = APIRouter()


@router.get("/")
async def list_alerts(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    level: Optional[int] = None,
    agent_id: Optional[str] = None,
    ip: Optional[str] = None,
    hours: Optional[int] = 24,
    sort_by: Optional[str] = Query(None, description="排序字段: timestamp, level"),
    sort_order: Optional[str] = Query(None, regex="^(asc|desc)$", description="排序方向: asc, desc"),
    db: Session = Depends(get_db)
):
    """获取 Wazuh 告警列表"""
    try:
        alert_service = AlertQueryService(db)

        # 计算时间范围
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours) if hours else None

        # 先查总数(limit=1)
        result = alert_service.get_alerts(
            offset=0,
            limit=1,
            level=level,
            agent_id=agent_id,
            start_time=start_time,
            end_time=end_time,
        )
        total_count = result.get("total", 0) if isinstance(result, dict) else len(result)

        # 根据 IP 查询实际数据
        if ip:
            result_data = alert_service.get_alerts_by_ip(
                ip=ip,
                offset=skip,
                limit=limit,
                sort_by=sort_by,
                sort_order=sort_order
            )
            alerts = result_data.get("items", []) if isinstance(result_data, dict) else result_data
        else:
            result_data = alert_service.get_alerts(
                offset=skip,
                limit=limit,
                level=level,
                agent_id=agent_id,
                start_time=start_time,
                end_time=end_time,
                sort_by=sort_by,
                sort_order=sort_order
            )
            alerts = result_data.get("items", []) if isinstance(result_data, dict) else result_data

        # 格式化响应
        formatted_alerts = []
        for alert in alerts:
            formatted_alerts.append({
                "id": alert.get("id") or alert.get("_id"),
                "timestamp": alert.get("timestamp") or alert.get("@timestamp"),
                "rule": {
                    "level": alert.get("rule", {}).get("level"),
                    "description": alert.get("rule", {}).get("description"),
                    "id": alert.get("rule", {}).get("id")
                },
                "agent": {
                    "id": alert.get("agent", {}).get("id"),
                    "name": alert.get("agent", {}).get("name"),
                    "ip": alert.get("agent", {}).get("ip")
                },
                "location": alert.get("location"),
                "full_log": alert.get("full_log")
            })

        return {
            "items": formatted_alerts,
            "total": total_count,
            "skip": skip,
            "limit": limit
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询告警失败: {str(e)}")


@router.get("/statistics")
async def get_alert_statistics(
    hours: int = Query(24, ge=1, le=720),
    db: Session = Depends(get_db)
):
    """获取告警统计信息"""
    try:
        alert_service = AlertQueryService(db)

        # 计算时间范围
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)

        stats = alert_service.get_alert_statistics(
            start_time=start_time,
            end_time=end_time
        )

        # 格式化统计结果
        return {
            "period": f"最近 {hours} 小时",
            "by_level": [
                {
                    "level": bucket["key"],
                    "count": bucket["doc_count"]
                }
                for bucket in stats["by_level"]
            ],
            "top_agents": [
                {
                    "agent": bucket["key"],
                    "count": bucket["doc_count"]
                }
                for bucket in stats["by_agent"]
            ],
            "top_rules": [
                {
                    "description": bucket["key"],
                    "count": bucket["doc_count"]
                }
                for bucket in stats["by_description"]
            ]
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询统计失败: {str(e)}")


@router.get("/{alert_id}")
async def get_alert(alert_id: str, db: Session = Depends(get_db)):
    """获取告警详情"""
    try:
        alert_service = AlertQueryService(db)
        alert = alert_service.get_alert_by_id(alert_id)

        return {
            "id": alert.get("_id"),
            "timestamp": alert.get("@timestamp"),
            "rule": alert.get("rule", {}),
            "agent": alert.get("agent", {}),
            "location": alert.get("location"),
            "full_log": alert.get("full_log"),
            "geoip": alert.get("geoip", {})
        }

    except Exception as e:
        raise HTTPException(status_code=404, detail=f"告警不存在: {str(e)}")


@router.post("/{alert_id}/create-incident")
async def create_incident_from_alert(
    alert_id: str,
    incident_data: dict,
    db: Session = Depends(get_db)
):
    """从告警创建事件"""
    # TODO: 实现从告警创建事件
    return {"message": "从告警创建事件 API", "alert_id": alert_id}
