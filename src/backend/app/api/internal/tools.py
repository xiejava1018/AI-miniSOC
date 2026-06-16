"""
Internal Agent Tools - 只读 SOC 工具集

三个工具:
- query_assets: 查询资产列表
- query_alerts: 查询 Wazuh 告警 (通过 OpenSearch)
- search_logs: 查询 Loki 日志
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.core.database import get_db
from app.core.config import settings
from app.models import Asset
from app.observability.metrics import tool_execution_count
from app.services.alert_query import AlertQueryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/tools", tags=["agent-tools"])


# ─────────────────────────────────────────────────────────────────────────────
# 依赖
# ─────────────────────────────────────────────────────────────────────────────

async def verify_service_token(request: Request) -> bool:
    """校验内部服务 Token (X-Service-Token)"""
    token = request.headers.get("X-Service-Token")
    expected = os.environ.get("INTERNAL_SERVICE_TOKEN", "")
    if not expected:
        # 未配置时跳过校验（POC 环境）
        return True
    if token != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized: invalid or missing X-Service-Token",
        )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic 请求/响应模型
# ─────────────────────────────────────────────────────────────────────────────

class QueryAssetsRequest(BaseModel):
    """查询资产请求"""
    ip: Optional[str] = None
    name: Optional[str] = None
    department: Optional[str] = None
    source: Optional[str] = None
    limit: int = 20
    offset: int = 0


class QueryAlertsRequest(BaseModel):
    """查询告警请求"""
    ip: Optional[str] = None
    level_min: int = 1
    level_max: int = 15
    rule_name: Optional[str] = None
    limit: int = 20
    offset: int = 0


class SearchLogsRequest(BaseModel):
    """查询日志请求"""
    query: str  # LogQL 查询
    start: Optional[int] = None  # ns timestamp
    end: Optional[int] = None
    limit: int = 100


# ─────────────────────────────────────────────────────────────────────────────
# Tool 1: query_assets
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/query_assets")
async def query_assets(
    req: QueryAssetsRequest,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_service_token),
) -> Dict[str, Any]:
    """
    查询资产列表

    支持按 IP、名称、部门、数据源过滤。
    仅返回只读字段，不修改任何数据。
    """
    try:
        q = db.query(Asset)
        if req.ip:
            q = q.filter(Asset.asset_ip.like(f"%{req.ip}%"))
        if req.name:
            q = q.filter(Asset.name.ilike(f"%{req.name}%"))
        if req.department:
            q = q.filter(Asset.business_unit.ilike(f"%{req.department}%"))
        if req.source:
            q = q.filter(Asset.data_source == req.source)

        total = q.count()
        assets = q.offset(req.offset).limit(req.limit).all()

        items = [
            {
                "id": str(a.id),
                "name": a.name or a.asset_ip,
                "ip": a.asset_ip,
                "mac": str(a.mac_address) if a.mac_address else None,
                "type": a.asset_type,
                "department": a.business_unit,
                "source": a.data_source,
                "status": a.asset_status,
                "criticality": a.criticality,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in assets
        ]

        tool_execution_count.labels(tool="query_assets", status="ok").inc()
        return {"ok": True, "data": {"total": total, "items": items}}

    except Exception as e:
        logger.exception("query_assets failed: %s", e)
        tool_execution_count.labels(tool="query_assets", status="error").inc()
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Tool 2: query_alerts
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/query_alerts")
async def query_alerts(
    req: QueryAlertsRequest,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_service_token),
) -> Dict[str, Any]:
    """
    查询 Wazuh 告警

    通过 AlertQueryService 查询 OpenSearch 中的 wazuh-alerts 索引。
    POC 阶段: 外部服务不可用时返回空数据，不抛出异常。
    """
    try:
        svc = AlertQueryService(db)

        # 计算时间范围 (默认最近 24 小时)
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=24)
        end_time = now

        result = svc.get_alerts(
            offset=req.offset,
            limit=req.limit,
            level=req.level_min if req.level_min > 1 else None,
            start_time=start_time,
            end_time=end_time,
            sort_by="timestamp",
            sort_order="desc",
        )

        # 按 IP 过滤 (AlertQueryService 不直接支持 IP 过滤，这里做内存过滤)
        items = result.get("items", [])
        if req.ip:
            items = [
                item for item in items
                if req.ip in (item.get("agent", {}).get("ip") or "")
            ]

        # 按 rule_name 过滤
        if req.rule_name:
            items = [
                item for item in items
                if req.rule_name.lower() in
                   (item.get("rule", {}).get("description") or "").lower()
            ]

        # 按等级过滤
        items = [
            item for item in items
            if req.level_min <= item.get("rule", {}).get("level", 0) <= req.level_max
        ]

        total = len(items)  # POC: 简化计数

        tool_execution_count.labels(tool="query_alerts", status="ok").inc()
        return {"ok": True, "data": {"total": total, "items": items}}

    except httpx.HTTPError as e:
        logger.warning("query_alerts OpenSearch unavailable: %s", e)
        tool_execution_count.labels(tool="query_alerts", status="degraded").inc()
        return {"ok": True, "data": {"total": 0, "items": []}, "degraded": True}

    except Exception as e:
        logger.exception("query_alerts failed: %s", e)
        tool_execution_count.labels(tool="query_alerts", status="error").inc()
        return {"ok": False, "error": str(e)}


# ─────────────────────────────────────────────────────────────────────────────
# Tool 3: search_logs
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/search_logs")
async def search_logs(
    req: SearchLogsRequest,
    db: Session = Depends(get_db),
    _auth: bool = Depends(verify_service_token),
) -> Dict[str, Any]:
    """
    查询 Loki 日志

    使用 LogQL 查询语法，支持时间范围过滤。
    时间戳使用纳秒级 Unix 时间戳。
    """
    try:
        now = datetime.now(timezone.utc)
        start_ns = req.start or int((now - timedelta(hours=1)).timestamp() * 1e9)
        end_ns = req.end or int(now.timestamp() * 1e9)

        loki_url = settings.LOKI_API_URL.rstrip("/")

        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                "query": req.query,
                "start": start_ns,
                "end": end_ns,
                "limit": req.limit,
            }
            resp = await client.get(
                f"{loki_url}/loki/api/v1/query_range",
                params=params,
            )

            if resp.status_code != 200:
                logger.warning("Loki returned %s: %s", resp.status_code, resp.text)
                tool_execution_count.labels(tool="search_logs", status="error").inc()
                return {"ok": False, "error": f"Loki error: {resp.status_code}"}

            data = resp.json()
            streams = data.get("data", {}).get("result", [])

            # 简化返回格式，提取关键信息
            items = []
            for stream in streams:
                labels = stream.get("stream", {})
                values = stream.get("values", [])
                for ts_ns, line in values:
                    items.append({
                        "timestamp": int(ts_ns) // 1_000_000,  # 转为 ms
                        "labels": labels,
                        "line": line,
                    })

            tool_execution_count.labels(tool="search_logs", status="ok").inc()
            return {
                "ok": True,
                "data": {
                    "streams": len(streams),
                    "items": items,
                    "stats": data.get("stats", {}),
                }
            }

    except httpx.TimeoutException:
        logger.warning("search_logs timeout: Loki %s", settings.LOKI_API_URL)
        tool_execution_count.labels(tool="search_logs", status="timeout").inc()
        return {"ok": False, "error": "Loki request timeout"}

    except Exception as e:
        logger.exception("search_logs failed: %s", e)
        tool_execution_count.labels(tool="search_logs", status="error").inc()
        return {"ok": False, "error": str(e)}