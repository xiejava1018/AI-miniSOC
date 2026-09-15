"""
告警管理 API (Wazuh集成)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
from app.core.database import get_db
from app.services.alert_query import AlertQueryService
from app.services.alert_sla import AlertSlaService

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
        # AlertSlaService 是无状态服务（db 随方法参数传入，非构造参数），
        # 实例化不传参；传了会报 "AlertSlaService() takes no arguments"。
        formatted_alerts = []
        sla_service = AlertSlaService()
        for alert in alerts:
            agent_ip = alert.get("agent", {}).get("ip")
            ts = alert.get("timestamp") or alert.get("@timestamp")
            sla_dict = None
            if agent_ip and ts:
                try:
                    if isinstance(ts, str):
                        ts_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    else:
                        ts_dt = ts
                    if ts_dt.tzinfo is None:
                        from datetime import timezone
                        ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                    sla_state = sla_service.compute_sla_for_alert(db, agent_ip, ts_dt)
                    sla_dict = sla_state.to_dict()
                except Exception:
                    # SLA 计算失败不影响告警主体返回
                    sla_dict = None
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
                    "ip": agent_ip
                },
                "location": alert.get("location"),
                "full_log": alert.get("full_log"),
                # === 治本方案：SLA 注入 ===
                "sla": sla_dict,
            })

        return {
            "items": formatted_alerts,
            "total": total_count,
            "skip": skip,
            "limit": limit
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询告警失败: {str(e)}")


@router.get("/sla-config")
async def get_sla_config():
    """返回 5 档业务影响的 SLA 配置（治本方案 · 2026-09-14）。

    前端用此端点渲染 SLA 设置页 / 详情页 SLA 倒计时颜色映射。
    配置源：app.core.criticality.BUSINESS_IMPACT_SLA（与评分/SLA 联动使用）
    """
    from app.core.criticality import (
        BUSINESS_IMPACT_SLA, BUSINESS_IMPACT_LABELS, BUSINESS_IMPACT_COLORS,
    )
    return {
        "items": [
            {
                "business_impact": code,
                "label": BUSINESS_IMPACT_LABELS[code],
                "color": BUSINESS_IMPACT_COLORS[code],
                **cfg,
            }
            for code, cfg in BUSINESS_IMPACT_SLA.items()
        ],
        "default_business_impact": "normal",
    }


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


@router.get("/trend")
async def get_alert_trend(
    hours: int = Query(24, ge=1, le=720),
    interval_hours: int = Query(1, ge=1, le=24),
    db: Session = Depends(get_db)
):
    """告警趋势(小时级聚合)"""
    try:
        service = AlertQueryService(db)
        trend = service.get_alert_trend(hours=hours, interval_hours=interval_hours)
        return {"trend": trend}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询趋势失败: {str(e)}")


@router.get("/top-assets")
async def get_top_alert_assets(
    hours: int = Query(24, ge=1, le=720),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """告警最多的资产 Top N"""
    try:
        service = AlertQueryService(db)
        assets = service.get_top_alert_assets(hours=hours, limit=limit)
        return {"assets": assets}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询Top资产失败: {str(e)}")


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
    incident_data: Optional[dict] = None,
    db: Session = Depends(get_db),
):
    """从单条告警创建事件（写 soc_incidents，按 agent.ip 关联 soc_asset_incidents）。

    可选 body: {severity?, assigned_to?, created_by?}；severity 缺省由 rule.level 推导。
    """
    from app.services.alert_incident_service import build_incident_from_alert, incident_to_dict
    body = incident_data or {}
    try:
        inc = build_incident_from_alert(
            db,
            alert_id,
            created_by=body.get("created_by") or "system",
            severity=body.get("severity"),
            assigned_to=body.get("assigned_to"),
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return incident_to_dict(inc)
