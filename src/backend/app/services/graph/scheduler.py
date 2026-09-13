"""
图谱 builder 定时任务（@track_task 包装 + asyncio 循环）

复用项目已有 task_observability 框架（§6.3 设计依据）：
  - decorator.py: @track_task 装饰器 + update_progress
  - bootstrap.py: lifespan 集成（启动对账 + 看门狗 + 通知消费）

调度策略（与 alert_group_snapshot_scheduler 同款 asyncio 循环）：
  - identity         每小时        依赖 soc_identity_events 增量
  - asset_port_vuln  每天 03:00    资产/端口/漏洞变更后 + 每日全量
  - topology         每天 04:00    同网段/同标签，年度重算
  - alert_group      每 6 小时     告警簇生成 + 老化清理
  - manual           每 6 小时     人工登记触发 + 校验
  - cleanup_expired  每 6 小时     删除过期边

启动位置（main.py lifespan）：
  - 在 ``bootstrap_task_observability()`` 之后
  - ``start_graph_builders()`` 启动所有循环任务
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.core.database import SessionLocal
from app.services.graph import delete_expired_edges
from app.services.graph.builders import (
    AlertGroupBuilder,
    AssetPortVulnBuilder,
    IdentityGraphBuilder,
    ManualRelationBuilder,
    TopologyBuilder,
)
from app.services.task_observability import (
    track_task,
    update_progress,
)

logger = logging.getLogger(__name__)


# 调度配置
IDENTITY_INTERVAL_S = 1 * 3600          # 1h
ASSET_PORT_VULN_CRON_HOUR = 3           # 每天 03:00
TOPOLOGY_CRON_HOUR = 4                  # 每天 04:00
ALERT_GROUP_INTERVAL_S = 6 * 3600       # 6h
MANUAL_INTERVAL_S = 6 * 3600            # 6h
CLEANUP_INTERVAL_S = 6 * 3600           # 6h
FIRST_RUN_DELAY = 60                     # 启动后 60s 首次跑

_tasks: list[asyncio.Task] = []


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# 6 个单跑任务（@track_task 包装，提供给手动触发 + asyncio 循环复用）
# ---------------------------------------------------------------------------


@track_task(
    task_key="graph_builder_identity",
    task_name="身份关系边构建（每小时）",
    task_type="scheduled",
    schedule_expr="@every 1h",
    expected_interval_s=IDENTITY_INTERVAL_S,
    timeout_s=300,
)
async def rebuild_identity_task() -> dict:
    """身份关系边构建（login_to / login_from / session_on / external_access / owned_by）"""
    db = SessionLocal()
    try:
        builder = IdentityGraphBuilder(db, window_days=30)
        stats = builder.rebuild_all()
        update_progress(stage="done", percent=100)
        logger.info("rebuild_identity_task done: %s", stats)
        return stats
    finally:
        db.close()


@track_task(
    task_key="graph_builder_asset_port_vuln",
    task_name="资产-端口-漏洞边构建（每日 03:00）",
    task_type="scheduled",
    schedule_expr="@daily 03:00",
    expected_interval_s=24 * 3600,
    timeout_s=900,
)
async def rebuild_asset_port_vuln_task() -> dict:
    """资产-端口-漏洞边构建（has_port / has_vuln / port_has_vuln）"""
    db = SessionLocal()
    try:
        builder = AssetPortVulnBuilder(db)
        stats = builder.rebuild_all()
        update_progress(stage="done", percent=100)
        logger.info("rebuild_asset_port_vuln_task done: %s", stats)
        return stats
    finally:
        db.close()


@track_task(
    task_key="graph_builder_topology",
    task_name="拓扑推断边构建（每日 04:00）",
    task_type="scheduled",
    schedule_expr="@daily 04:00",
    expected_interval_s=24 * 3600,
    timeout_s=600,
)
async def rebuild_topology_task() -> dict:
    """拓扑推断边构建（same_segment / shared_tag）"""
    db = SessionLocal()
    try:
        builder = TopologyBuilder(db)
        stats = builder.rebuild_all()
        update_progress(stage="done", percent=100)
        logger.info("rebuild_topology_task done: %s", stats)
        return stats
    finally:
        db.close()


@track_task(
    task_key="graph_builder_alert_group",
    task_name="告警簇聚合边构建（每6小时）",
    task_type="scheduled",
    schedule_expr="@every 6h",
    expected_interval_s=ALERT_GROUP_INTERVAL_S,
    timeout_s=600,
)
async def rebuild_alert_group_task() -> dict:
    """告警簇聚合边构建（alerted_on / co_alerted）"""
    db = SessionLocal()
    try:
        builder = AlertGroupBuilder(db)
        stats = builder.rebuild_all()
        update_progress(stage="done", percent=100)
        logger.info("rebuild_alert_group_task done: %s", stats)
        return stats
    finally:
        db.close()


@track_task(
    task_key="graph_builder_manual",
    task_name="人工登记关系校验（每6小时）",
    task_type="scheduled",
    schedule_expr="@every 6h",
    expected_interval_s=MANUAL_INTERVAL_S,
    timeout_s=300,
)
async def rebuild_manual_task() -> dict:
    """人工登记关系校验（belongs_to_system / runs_on / owned_by / system_owned_by）"""
    db = SessionLocal()
    try:
        builder = ManualRelationBuilder(db)
        stats = builder.rebuild_all()
        update_progress(stage="done", percent=100)
        logger.info("rebuild_manual_task done: %s", stats)
        return stats
    finally:
        db.close()


@track_task(
    task_key="graph_cleanup_expired_edges",
    task_name="过期边清理（每6小时）",
    task_type="scheduled",
    schedule_expr="@every 6h",
    expected_interval_s=CLEANUP_INTERVAL_S,
    timeout_s=120,
)
async def cleanup_expired_edges_task() -> dict:
    """删除 expires_at < now() 的边（观测类边按窗口衰减淘汰）"""
    db = SessionLocal()
    try:
        deleted = delete_expired_edges(db)
        db.commit()
        update_progress(stage="done", percent=100)
        logger.info("cleanup_expired_edges_task deleted=%d", deleted)
        return {"deleted": deleted}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# asyncio 循环（启动后 60s 首跑，之后按各自间隔触发）
# 与 alert_group_snapshot_scheduler._loop 同款范式
# ---------------------------------------------------------------------------


async def _interval_loop(task_fn, interval_s: int, name: str) -> None:
    """固定间隔循环：先首跑，再每 interval_s 跑一次。"""
    logger.info("graph loop [%s] started, interval=%ds", name, interval_s)
    while True:
        try:
            await task_fn()
        except asyncio.CancelledError:
            logger.info("graph loop [%s] cancelled", name)
            raise
        except Exception:
            logger.exception("graph loop [%s] iteration failed", name)
        await asyncio.sleep(interval_s)


async def _daily_loop(task_fn, hour: int, minute: int, name: str) -> None:
    """每天指定时刻跑：先首跑 + 等到下一个 hour:minute，再每天跑。"""
    logger.info("graph loop [%s] started, cron=%02d:%02d", name, hour, minute)
    while True:
        try:
            now = _utcnow()
            # 计算下次执行时刻
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target = target.replace(day=now.day + 1)  # 明天
            wait_s = (target - now).total_seconds()
            await asyncio.sleep(wait_s)
            await task_fn()
        except asyncio.CancelledError:
            logger.info("graph loop [%s] cancelled", name)
            raise
        except Exception:
            logger.exception("graph loop [%s] iteration failed", name)
            await asyncio.sleep(60)  # 出错后等 60s 再重试


async def start_graph_builders() -> None:
    """启动所有 builder 循环（幂等：重复调用不会启动多份）。

    首跑延迟 60s 启动，让主进程先把基础服务起来。
    """
    global _tasks
    if _tasks:
        return  # 已启动

    # 首跑延迟后并行启动各循环
    async def _start_all():
        await asyncio.sleep(FIRST_RUN_DELAY)
        _tasks.extend([
            asyncio.create_task(_interval_loop(
                rebuild_identity_task, IDENTITY_INTERVAL_S, "identity")),
            asyncio.create_task(_daily_loop(
                rebuild_asset_port_vuln_task,
                ASSET_PORT_VULN_CRON_HOUR, 0, "asset_port_vuln")),
            asyncio.create_task(_daily_loop(
                rebuild_topology_task,
                TOPOLOGY_CRON_HOUR, 0, "topology")),
            asyncio.create_task(_interval_loop(
                rebuild_alert_group_task, ALERT_GROUP_INTERVAL_S, "alert_group")),
            asyncio.create_task(_interval_loop(
                rebuild_manual_task, MANUAL_INTERVAL_S, "manual")),
            asyncio.create_task(_interval_loop(
                cleanup_expired_edges_task, CLEANUP_INTERVAL_S, "cleanup_expired")),
        ])
        logger.info("graph builders started: 6 loops")

    asyncio.create_task(_start_all())


async def stop_graph_builders() -> None:
    """停止所有 builder 循环（lifespan shutdown 调用）。"""
    global _tasks
    for t in _tasks:
        if not t.done():
            t.cancel()
    for t in _tasks:
        try:
            await t
        except asyncio.CancelledError:
            pass
    _tasks = []
    logger.info("graph builders stopped")