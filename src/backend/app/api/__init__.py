"""
API 路由汇总
"""

from fastapi import APIRouter
from app.api import assets, incidents, alerts, ai

api_router = APIRouter()

# 注册各个模块的路由
api_router.include_router(assets.router, prefix="/assets", tags=["资产管理"])
api_router.include_router(incidents.router, prefix="/incidents", tags=["事件管理"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["告警管理"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI分析"])
