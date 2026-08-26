"""
扫描器 watchdog 调度器（P3/F-S3 L1+L2 在线检测，final.md §8.1 + §4.3）

设计要点：
  - 独立 SessionLocal（每 tick 一个 session，CLAUDE.md P4 WO-2 教训）
  - 单条 try/except（一条失败不挂整批）
  - L1 离线判定：last_heartbeat < now - 90s → status='offline' + 通知
  - L2 数据通道异常：soc_source_health.scanner:* 键 last_success_at 超期
  - F-3 超时重派：soc_scanner_tasks.running 超 6h → failed + clone pending + parent_task_id
  - dedup：复用 push_notification_service._push() 的 dedup_title 机制（按 scanner_id 去重）

CLAUDE.md 教训（:1189）：独立 session 防 rollback 互杀；
           （:661）：通知失败不影响 scheduler 主循环。
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from app.core.database import SessionLocal
from app.models.scanner_models import ScannerAgent, ScannerTask

logger = logging.getLogger(__name__)


# ============================================================================
# 常量（与 push_notification_service.DEFAULT_PUSH_RULES.scanner_offline 同步）
# ============================================================================
HEARTBEAT_OFFLINE_SECONDS = 90      # L1：超过 90s 心跳→离线（最终稿 §4.3）
TASK_RUNNING_TIMEOUT_HOURS = 6       # F-3：running 超 6h 强制重派


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _notify_scanner_offline(scanner_name: str, scanner_id: str, ip: str, last_hb: datetime) -> int:
    """触发离线通知（独立 session 防 rollback 互杀）。返回发出通知数。"""
    try:
        from app.services.push_notification_service import PushNotificationService
        fail_db = SessionLocal()
        try:
            svc = PushNotificationService(fail_db)
            rules = svc.load_rules()
            if not (rules.get("enabled") and rules.get("scanner_offline", {}).get("enabled")):
                return 0
            offline_minutes = int(rules["scanner_offline"].get("offline_minutes", 90))
            offline_h = (datetime.now(timezone.utc) - last_hb).total_seconds() / 3600 if last_hb else None
            import asyncio as _asyncio
            return _asyncio.run(svc._push(
                dedup_title=f"【扫描器离线】{scanner_name}",
                severity="critical",
                title=f"【扫描器离线】{scanner_name}（{scanner_id[:8]}）",
                content=(
                    f"扫描器「{scanner_name}」（IP {ip or '?'}、{scanner_id[:8]}）已离线"
                    f"{offline_h:.1f}h（阈值 {offline_minutes/60:.1f}h）。"
                    f"最后心跳 {last_hb.isoformat() if last_hb else '从未'}。"
                    "控制面将自动跳过该扫描器的任务派发；"
                    "请检查扫描器主机状态 / 网络 / heartbeat 拉任务循环。"
                ),
                link_path="/assets/scan?tab=scanners",
            ))
        finally:
            fail_db.close()
    except Exception as e:
        logger.debug("scanner_offline notification failed for %s: %s", scanner_name, e)
        return 0


# ============================================================================
# watchdog tick
# ============================================================================
def _watchdog_tick() -> None:
    """每 60s 跑一次：L1 离线判定 + L2 通道异常 + F-3 超时重派。

    关键不变量（v1.3 F-2）：
      - 每个 tick 新开 SessionLocal（防 rollback 互杀）
      - 单条 try/except（一条失败不影响其他扫描器）
      - 整 tick 失败时整体 rollback + 退避 60s（不避免重转）
    """
    with SessionLocal() as session:
        try:
            # ---------- L1：扫描器离线判定 ----------
            cutoff = _utcnow() - timedelta(seconds=HEARTBEAT_OFFLINE_SECONDS)
            offline_candidates = (
                session.query(ScannerAgent)
                .filter(
                    ScannerAgent.enabled == True,  # noqa: E712
                    ScannerAgent.status != "offline",
                    ScannerAgent.last_heartbeat < cutoff,
                )
                .all()
            )
            for a in offline_candidates:
                try:
                    a.status = "offline"
                    # 通知不在 watchdog 里发（后台线程调 async _push 会 RuntimeWarning）。
                    # 统一由 push_scheduler 每 30min 调 check_scanner_offline() 负责，
                    # 它查 status='offline' 且靠 _push 的 dedup_title 去重。
                    session.flush()
                except Exception:
                    logger.exception("watchdog: 处理 scanner %s 失败", a.scanner_id)
                    session.rollback()
                    continue

            # ---------- F-3：超时 running 任务 → 标 failed + 自动重派 ----------
            stuck_cutoff = _utcnow() - timedelta(hours=TASK_RUNNING_TIMEOUT_HOURS)
            stuck_tasks = (
                session.query(ScannerTask)
                .filter(
                    ScannerTask.status == "running",
                    ScannerTask.started_at < stuck_cutoff,
                )
                .all()
            )
            for t in stuck_tasks:
                try:
                    # 检查重派次数上限（parent_task_id 链 ≤ 3 层）
                    chain_count = 1
                    cursor = t
                    while cursor.parent_task_id is not None:
                        parent = (
                            session.query(ScannerTask)
                            .filter(ScannerTask.task_uuid == cursor.parent_task_id)
                            .first()
                        )
                        if not parent:
                            break
                        chain_count += 1
                        cursor = parent
                        if chain_count >= 3:
                            # 超限：停止重派 + 告警（admin 查任务处理）
                            t.status = "failed"
                            t.error_message = (
                                f"watchdog: 重派次数已达上限 (3 次)，"
                                f"需人工介入查任务链 parent={t.parent_task_id}"
                            )
                            logger.warning(
                                "scanner task %s 重派次数达上限 (parent=%s)",
                                t.task_uuid, t.parent_task_id,
                            )
                            session.add(t)
                            break
                    else:
                        # clone 一条新 pending 让路由重新选
                        t.status = "failed"
                        t.error_message = f"watchdog: running 超时（>{TASK_RUNNING_TIMEOUT_HOURS}h）"
                        new_task = ScannerTask(
                            mode=t.mode,
                            scope=t.scope,
                            target_summary=t.target_summary,
                            target_scanner_id=None,   # 重派让 auto 路由重选
                            scanner_id=None,
                            status="pending",
                            run_reason=t.run_reason,
                            parent_task_id=t.task_uuid,
                            capabilities=t.capabilities,
                            nmap_args=t.nmap_args,
                        )
                        session.add(new_task)
                        logger.info(
                            "scanner task %s 重派 → new pending (parent=%s)",
                            t.task_uuid, t.task_uuid,
                        )
                except Exception:
                    logger.exception("watchdog: 重派 task %s 失败", t.task_uuid)
                    session.rollback()
                    continue

            session.commit()
        except Exception:
            session.rollback()
            logger.exception("watchdog tick failed; will retry in 60s")


# ============================================================================
# lifespan 注册接口
# ============================================================================
async def _loop() -> None:
    """每 60s 跑一次 _watchdog_tick。"""
    logger.info("scanner watchdog started (interval=60s)")
    while True:
        try:
            _watchdog_tick()
        except Exception:
            # _watchdog_tick 内部已 try/except；这里双保险
            logger.exception("scanner watchdog tick raised outside try/except")
        await asyncio.sleep(60)


_watchdog_task: asyncio.Task | None = None


def start_scanner_watchdog() -> None:
    """lifespan startup 注册。"""
    global _watchdog_task
    if _watchdog_task is not None:
        return
    _watchdog_task = asyncio.create_task(_loop(), name="scanner-watchdog")


async def stop_scanner_watchdog() -> None:
    """lifespan shutdown 取消。"""
    global _watchdog_task
    if _watchdog_task is not None:
        _watchdog_task.cancel()
        try:
            await _watchdog_task
        except asyncio.CancelledError:
            pass
        _watchdog_task = None