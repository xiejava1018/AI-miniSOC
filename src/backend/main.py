"""
FastAPI 主应用入口
"""
from dotenv import load_dotenv
import os
import logging
from contextlib import asynccontextmanager

# 加载环境变量
load_dotenv()

# 配置应用日志（默认 INFO，让后台检测任务日志可见）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.response_wrapper import ResponseWrapperMiddleware
from app.api import api_router
from app.services.browsing_detection import (
    start_browsing_detector,
    stop_browsing_detector,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动/停止后台任务"""
    start_browsing_detector()
    try:
        yield
    finally:
        await stop_browsing_detector()


# 创建 FastAPI 应用实例
app = FastAPI(
    title="AI-miniSOC API",
    description="AI驱动的微型安全运营中心",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# 注册响应包装中间件（必须在CORS之前）
app.add_middleware(ResponseWrapperMiddleware)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(api_router, prefix="/api/v1")

# 注册可观测性路由（/metrics 等）
from app.api.metrics import router as metrics_router
app.include_router(metrics_router)


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "AI-miniSOC API",
        "version": "0.1.0",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "service": "ai-minisoc-backend"
    }
