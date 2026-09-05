"""
FastAPI 主应用入口
"""
from dotenv import load_dotenv
import os
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

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
from app.services.alert_group_snapshot_scheduler import (
    start_alert_group_snapshot,
    stop_alert_group_snapshot,
)
from app.services.alert_digest_scheduler import (
    start_alert_digest_scheduler,
    stop_alert_digest_scheduler,
)
from app.services.cisa_kev_service import (
    start_cisa_kev_scheduler,
    stop_cisa_kev_scheduler,
)
from app.services.push_scheduler import (
    start_push_scheduler,
    stop_push_scheduler,
)
# P3 资产扫描：scanner watchdog + 中央调度（final.md §8）
from app.services.scanner_watchdog_scheduler import (
    start_scanner_watchdog,
    stop_scanner_watchdog,
)
from app.services.central_scan_scheduler import (
    start_central_scan_scheduler,
    stop_central_scan_scheduler,
)
from app.services.task_observability import (
    bootstrap_task_observability,
    shutdown_task_observability,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动/停止后台任务。

    启动顺序（v0.4.2）：
    1. 单 worker 部署约束检查
    2. 任务可观测性启动（启动对账 + watchdog + notification drain）
       ★ 必须在业务 scheduler 启动之前，先把残留 running run 标 unknown
    3. 业务 schedulers
    """
    from app.services.single_worker_guard import check_single_worker_or_warn
    check_single_worker_or_warn()

    # 模型自建表（路径 B 即时落地，P3 资产扫描控制面/数据面 final.md §5.6）：
    # 确保所有 models/*.py 中定义的表（包括 P3 ScannerTask/ScanTarget/ScanFinding/ScannerAgent）
    # 在生产库存在。create_all 仅建缺失表，不动已有表与数据，与 P4 治理保持一致。
    # ★ 必须在 bootstrap_task_observability 之前——后者依赖 sync_task 字典表的 status 列。
    from app.core.database import engine
    import app.models  # noqa: F401  触发所有 model 的 import，确保 Base.metadata 注册
    from app.models.base import Base as _Base
    _Base.metadata.create_all(engine)
    logging.getLogger(__name__).info("metadata.create_all done; tables=%d",
                                    len(_Base.metadata.tables))

    # 任务可观测性：启动对账 + watchdog + notification drain
    obs_stats = await bootstrap_task_observability()
    logging.getLogger(__name__).info("task observability bootstrapped: %s", obs_stats)

    start_browsing_detector()
    # 行为画像：每日快照 + 水位回溯补拉（§9.3，含启动即补）
    from app.services.behavior_profile import start_behavior_profile_scheduler
    start_behavior_profile_scheduler()
    start_alert_group_snapshot()
    start_alert_digest_scheduler()
    start_cisa_kev_scheduler()
    start_push_scheduler()
    # P3 资产扫描：L1+L2 在线检测（每 60s）+ 每天 03:00/04:00 自动建任务
    start_scanner_watchdog()
    start_central_scan_scheduler()
    try:
        yield
    finally:
        await stop_browsing_detector()
        from app.services.behavior_profile import stop_behavior_profile_scheduler
        stop_behavior_profile_scheduler()
        await stop_alert_group_snapshot()
        await stop_alert_digest_scheduler()
        await stop_cisa_kev_scheduler()
        await stop_push_scheduler()
        # P3 资产扫描：shutdown
        await stop_central_scan_scheduler()
        await stop_scanner_watchdog()
        # 任务可观测性最后关，保证业务 scheduler 完结后的 run 能被对账
        await shutdown_task_observability()


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

# ---------------------------------------------------------------------------
# MCP Server (纯 C 路线)
#   http://:8100/sse  — 手写 28 个 tools（SSE transport，Token 管理 + AI + Loki）
#   详见 app/mcp/server.py
# ---------------------------------------------------------------------------
from app.mcp import mount_mcp
from app.mcp.token_manager import get_token_manager
from contextlib import asynccontextmanager as _asg_lcm


@_asg_lcm
async def _mcp_lifespan(_app):
    """MCP 专属生命周期：启动 TokenManager 后台线程 + 清理"""
    yield
    get_token_manager().shutdown()


# 把 MCP lifespan 合并进主 lifespan
_orig_lifespan = app.router.lifespan_context
@_asg_lcm
async def _combined_lifespan(_app):
    async with _orig_lifespan(_app):
        try:
            yield
        finally:
            get_token_manager().shutdown()

app.router.lifespan_context = _combined_lifespan

_mcp_info = mount_mcp(app, mount_path="/mcp")
logging.getLogger(__name__).info("MCP ready: %s", _mcp_info.get("endpoints"))


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
    """健康检查（v0.4.2）。

    - healthy:  200，全部正常
    - degraded: 200，部分任务 stale / 单个 zombie（容器保留，运维介入）
    - down:     503，多个 zombie / 看门狗自身挂 / DB 不可达（容器可重启、LB 摘流量）
    """
    from fastapi.responses import JSONResponse
    from app.core.database import SessionLocal
    from app.models.task_observability import SocTaskRegistry, SocTaskRun, TaskRunStatus
    from app.services.task_observability.metrics import task_watchdog_alive
    from sqlalchemy import select, func as sa_func
    import time

    body: dict = {
        "status": "healthy",
        "service": "ai-minisoc-backend",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "watchdog": {"alive": True, "last_tick_seconds_ago": None, "clock_skew_seconds": 0},
        "stale_tasks": [],
        "zombies": [],
        "disabled_tasks": [],
    }
    http_code = 200

    try:
        db = SessionLocal()
        try:
            from app.services.task_observability.watchdog import WATCHDOG_TASK_KEY
            now = datetime.now(timezone.utc)

            # zombie runs
            zombies = db.execute(
                select(SocTaskRun).where(SocTaskRun.status == TaskRunStatus.ZOMBIE)
            ).scalars().all()
            body["zombies"] = [
                {"task_key": z.task_key, "run_id": str(z.id), "started_at": z.started_at.isoformat() if z.started_at else None}
                for z in zombies
            ]

            # stale registry
            stale = []
            for reg in db.execute(select(SocTaskRegistry).where(SocTaskRegistry.enabled.is_(True))).scalars():
                if reg.task_key == WATCHDOG_TASK_KEY or not reg.expected_interval_s:
                    continue
                ref = reg.last_run_at or reg.created_at
                if ref and (now - ref).total_seconds() > 2 * reg.expected_interval_s:
                    stale.append({
                        "task_key": reg.task_key,
                        "last_run_at": ref.isoformat() if ref else None,
                        "expected_interval_s": reg.expected_interval_s,
                    })
            body["stale_tasks"] = stale

            # disabled
            disabled = db.execute(
                select(SocTaskRegistry.task_key).where(SocTaskRegistry.enabled.is_(False))
            ).scalars().all()
            body["disabled_tasks"] = list(disabled)

            # watchdog last tick —— 从指标当前值拿不到，用 registry 推断
            wd = db.get(SocTaskRegistry, WATCHDOG_TASK_KEY)
            if wd and wd.last_run_at:
                body["watchdog"]["last_tick_seconds_ago"] = int((now - wd.last_run_at).total_seconds())
                if (now - wd.last_run_at).total_seconds() > 180:
                    body["watchdog"]["alive"] = False
        finally:
            db.close()
    except Exception as e:
        body["status"] = "down"
        body["error"] = f"db unreachable: {type(e).__name__}: {e}"
        return JSONResponse(status_code=503, content=body)

    # 状态判定
    n_zombie = len(body["zombies"])
    n_stale = len(body["stale_tasks"])
    wd_alive = body["watchdog"]["alive"]

    if not wd_alive or n_zombie >= 3:
        body["status"] = "down"
        http_code = 503
    elif n_zombie > 0 or n_stale > 0:
        body["status"] = "degraded"
        http_code = 200
    else:
        body["status"] = "healthy"
        http_code = 200

    return JSONResponse(status_code=http_code, content=body)
