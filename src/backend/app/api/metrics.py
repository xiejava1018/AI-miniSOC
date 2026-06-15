"""
可观测性 API

提供 Prometheus 指标端点
"""

from fastapi import APIRouter, Response
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

router = APIRouter(prefix="", tags=["可观测性"])


@router.get("/metrics")
async def metrics():
    """
    Prometheus 指标端点

    返回所有已注册指标的当前值,格式遵循 Prometheus 采集规范
    """
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )