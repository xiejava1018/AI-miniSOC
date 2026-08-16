"""
单 worker 部署约束（P3-T4）

AI-miniSOC 当前所有后台调度器（browsing 检测 / alert snapshot / digest / KEV）
均为**进程内内存型**调度器（_task 全局变量、_cache 进程级、_schema_ensured 开关等）。
多 worker（uvicorn --workers N>1）部署会引发：
- 调度器重复执行（与 P1-T4 唯一约束叠加仍可能产生重复事件）
- KEV 缓存、source_health 内存统计等状态不一致
- 运行时 DDL 竞态（已通过 P1-T2 收口迁移化消除）

P3-T4 验收路径二选一：
- A. 文档化单 worker 约束（启动时检测 + 警告日志，文档写明）
- B. 加轻量分布式锁（PG 行锁，避免重复执行）

本模块实现 A，启动时若检测到 WORKERS > 1 打 ERROR 日志（不阻塞启动，
因为反正是开发用、生产前会看日志）；同时提供 PG 行锁 helper（路径 B
的备用方案，留给后续需要时接入）。
"""
import logging
import os

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# 单 worker 启动告警阈值（从环境变量读取，与 uvicorn --workers 配合）
ENV_WORKERS = "UVICORN_WORKERS"  # 由部署脚本在启动 uvicorn 时同步写入


def check_single_worker_or_warn() -> None:
    """启动时调用：若检测到 WORKERS > 1，打 ERROR 日志（不抛错）。

    调用点：app/main.py lifespan 启动处。
    """
    workers = os.environ.get(ENV_WORKERS, "1")
    try:
        n = int(workers)
    except ValueError:
        n = 1
    if n > 1:
        logger.error(
            "P3-T4: 检测到 UVICORN_WORKERS=%d > 1。当前后台调度器（browsing/alert/KEV）"
            "均为进程内单例，多 worker 部署会导致调度重复执行与状态漂移。"
            "生产部署请设 WORKERS=1，或为调度器接入分布式锁（见 single_worker_guard.py）。",
            n,
        )
    else:
        logger.info("P3-T4: 单 worker 启动正常（UVICORN_WORKERS=%d）。", n)


# ─────────────────────────────────────────────────
# 备用：PG 行锁 helper（路径 B，留给后续接入）
# ─────────────────────────────────────────────────

_LOCK_KEY_SCHEDULER = "scheduler:lease"


def try_acquire_scheduler_lease(db: Session, owner: str, ttl_seconds: int = 60) -> bool:
    """尝试获取调度器租约（PG 行锁的轻量级实现）。

    Returns: True=获取成功；False=已被其他 worker 占用。
    """
    # 用 PG advisory lock 的简化版：维护一行 lease 表（key=唯一）
    # 实际接入时需要先建表 soc_scheduler_lease，目前保留接口。
    # 当前 P3-T4 不实现 B 路径，仅留函数 stub。
    raise NotImplementedError(
        "分布式锁路径（B）本期不实现，依赖 A（单 worker 部署）。"
        "需要时见 single_worker_guard.py 注释扩展。"
    )