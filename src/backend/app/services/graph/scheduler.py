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
import threading
from datetime import datetime, timedelta, timezone
from typing import Callable

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

# 全进程 builder 串行锁（2026-09-14 v1.8 修订）：
# 必须用 **threading.Lock 且在工作线程内获取**，不能用 asyncio.Semaphore——
# @track_task 的 timeout 会 cancel 协程，asyncio 锁会随 cancel 提前释放，
# 但 asyncio.to_thread 的工作线程不可中断、仍在写库，导致下一个 builder 进临界区，
# 两个全量重建在 soc_graph_nodes 上行锁互等（Lock/transactionid）。
# threading.Lock 随线程生命周期严格持有：前一个线程不结束，后一个拿不到锁。
_builder_thread_lock = threading.Lock()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class _BuilderBusy(RuntimeError):
    """另一个 builder 正在跑（非阻塞获取锁失败）。"""


def _run_builder_in_thread(
    fn: Callable[[], dict], name: str, *, wait: bool = True
) -> dict:
    """在线程工作函数内部串行获取锁 + 创建/提交/回滚/关闭独立 Session（**同步**）。

    关键：
      - threading.Lock 在工作线程内获取，不被 asyncio cancel 提前释放。
      - Session 也在工作线程里创建并关闭（Session/连接不跨线程共享）。
      - 成功 commit、异常 rollback、finally close，杜绝 idle in transaction 僵尸。

    Args:
        wait: True 拿不到锁就阻塞等（HTTP /rebuild 需要拿结果）；
              False 拿不到立即抛 _BuilderBusy（定时任务本轮跳过，下轮再试）。
    """
    if wait:
        _builder_thread_lock.acquire()
    elif not _builder_thread_lock.acquire(blocking=False):
        logger.warning("graph builder [%s] skipped: another builder is running", name)
        raise _BuilderBusy(name)
    try:
        db = SessionLocal()
        try:
            result = fn(db)
            db.commit()
            return result
        except Exception:
            db.rollback()
            logger.exception("graph builder [%s] failed (rolled back)", name)
            raise
        finally:
            db.close()
    finally:
        _builder_thread_lock.release()


async def _offload(fn: Callable[[], dict], name: str) -> dict:
    """定时循环专用 offload。

    - 非阻塞抢锁：另一个 builder 在跑时本轮直接跳过（下轮再试），不堆积。
    - 异常不抱（返回 error dict），不让 asyncio 循环崩。
    """
    return await run_builder_async(fn, name, raise_on_error=False, wait=False)


async def run_builder_async(
    fn: Callable[[], dict], name: str, *,
    raise_on_error: bool = False, wait: bool = True,
) -> dict:
    """对外的 builder offload 入口（调度循环与 HTTP /rebuild 共用）。

    串行保证来自工作线程内的 ``_builder_thread_lock``（threading.Lock），
    **全进程任意时刻只有一个全量重建事务在跑**。锁在不可中断的工作线程内
    获取/释放，不会被 @track_task 的 timeout-cancel 提前释放（曾因此导致两个
    identity builder 并发、在 soc_graph_nodes 行锁互等）。

    Args:
        fn: 接收 ``db: Session`` 的同步工作函数。
        name: 日志用名称。
        wait: True 拿不到锁就等（HTTP 端点要拿结果）；False 抢不到立即返回
              ``{"skipped": ...}``（定时任务本轮跳过）。
        raise_on_error: True 时异常向上抛（HTTP 返回 500）；False 返回 error dict。
    """
    logger.info("graph builder [%s] queued (offloaded to thread, wait=%s)", name, wait)
    t0 = _utcnow()
    try:
        result = await asyncio.to_thread(_run_builder_in_thread, fn, name, wait=wait)
        logger.info("graph builder [%s] done in %.1fs", name,
                    (_utcnow() - t0).total_seconds())
        return result
    except _BuilderBusy:
        return {"skipped": "another builder is running"}
    except Exception as exc:
        logger.error("graph builder [%s] failed after %.1fs: %s",
                     name, (_utcnow() - t0).total_seconds(), exc)
        if raise_on_error:
            raise
        return {"error": exc.__class__.__name__}


# ---------------------------------------------------------------------------
# 6 个单跑任务（@track_task 包装，提供给手动触发 + asyncio 循环复用）
#
# v1.8（2026-09-13）：所有同步 builder 代码经 asyncio.to_thread 在线程池跑，
# 不再阻塞 uvicorn 单 worker event loop；事务在工作线程内 commit/rollback。
# ---------------------------------------------------------------------------


@track_task(
    task_key="graph_builder_identity",
    task_name="身份关系边构建（每小时）",
    task_type="scheduled",
    schedule_expr="@every 1h",
    expected_interval_s=IDENTITY_INTERVAL_S,
    timeout_s=900,
)
async def rebuild_identity_task() -> dict:
    """身份关系边构建（login_to / login_from / session_on / external_access / owned_by）"""
    return await _offload(
        lambda db: IdentityGraphBuilder(db, window_days=30).rebuild_all(),
        "identity",
    )


@track_task(
    task_key="graph_builder_asset_port_vuln",
    task_name="资产-端口-漏洞边构建（每日 03:00）",
    task_type="scheduled",
    schedule_expr="@daily 03:00",
    expected_interval_s=24 * 3600,
    timeout_s=900,
)
async def rebuild_asset_port_vuln_task() -> dict:
    """资产-端口-漏洞边构建（has_port / has_vuln / port_has_vuln）。

    每日任务用 wait=True：撞车时排队等锁，保证当天必跑（而不是 skip 后等明天）。
    """
    return await run_builder_async(
        lambda db: AssetPortVulnBuilder(db).rebuild_all(),
        "asset_port_vuln", wait=True,
    )


@track_task(
    task_key="graph_builder_topology",
    task_name="拓扑推断边构建（每日 04:00）",
    task_type="scheduled",
    schedule_expr="@daily 04:00",
    expected_interval_s=24 * 3600,
    timeout_s=900,
)
async def rebuild_topology_task() -> dict:
    """拓扑推断边构建（same_segment / shared_tag）。

    每日任务 wait=True（当天必跑）；实测 73 台资产产生 ~2863 条推断边，
    单边 upsert 串行约 6 分钟，timeout 放宽到 900s。
    """
    return await run_builder_async(
        lambda db: TopologyBuilder(db).rebuild_all(), "topology", wait=True,
    )


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
    return await _offload(lambda db: AlertGroupBuilder(db).rebuild_all(), "alert_group")


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
    return await _offload(lambda db: ManualRelationBuilder(db).rebuild_all(), "manual")


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
    def _work(db) -> dict:
        deleted = delete_expired_edges(db)
        update_progress(stage="done", percent=100)
        logger.info("cleanup_expired_edges_task deleted=%d", deleted)
        return {"deleted": deleted}

    return await _offload(_work, "cleanup_expired")


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
    """每天指定时刻跑：等到下一个 hour:minute，再每天跑。

    v1.8 修复：原 ``target.replace(day=now.day+1)`` 在月末会抛 ValueError，
    改用 timedelta(days=1) 跨月安全。
    """
    logger.info("graph loop [%s] started, cron=%02d:%02d", name, hour, minute)
    while True:
        try:
            now = _utcnow()
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target = target + timedelta(days=1)  # 明天（跨月安全）
            wait_s = (target - now).total_seconds()
            await asyncio.sleep(wait_s)
            await task_fn()
            # 跑完后再睡到明天同一时刻
            await asyncio.sleep(1)
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