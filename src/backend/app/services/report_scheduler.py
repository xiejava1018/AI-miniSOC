"""
安全报告自动生成调度器（weekly / monthly）

背景
----
四种报告触发类型里，`on_demand`（用户点按钮）与 `incident_driven`
（事件驱动，有独立端点供外部 cron 调）都是活的，但 `weekly` / `monthly`
此前**没有任何调度器**——只能由用户在报告列表页手动点「生成」。
这与「老板每周要一份报告，报告自动出」的产品意图不符。

本调度器补齐这一段：每天定点巡检一次，到了该出周报/月报的日子就生成一份，
生成后由 push_scheduler 的场景5（报告生成完成）推站内信给用户——
即「报告自动出，异常主动来」闭环打通。

设计（严格复用 alert_digest_scheduler / push_scheduler 范式）
--------------------------------------------------------------
- start_report_scheduler()  : 启动（幂等，受 REPORT_SCHEDULER_ENABLED 控制）
- stop_report_scheduler()   : 停止
- run_report_once()         : 手动触发单轮（不依赖调度，供 API / 测试 / 验证）

★ 幂等是本调度器的核心难点
----------------------------
「今天该出周报」不等于「今天要出一份周报」——服务重启、部署、定时器重入
都可能让同一轮跑多次。若无脑生成，用户会收到 N 份一模一样的周报。

因此引入 **period key** 概念：
- weekly  → 形如 ``2026-W42``（ISO 周）
- monthly → 形如 ``2026-11``（自然月）

生成前先查「该 period 是否已存在报告」，存在则跳过。这样：
- 重复触发安全
- 进程重启不会重出
- 手动触发过一次后，调度器当天不会再出

**不依赖数据库唯一约束**：soc_security_reports 上没有 (report_type, period) 唯一
约束（只有普通索引），所以幂等靠应用层查询保证。加约束需要迁移 + 存量数据
清洗，收益不抵风险。

规则外置
--------
全部可调项放在 ``soc_system_config(category='reports')``，读法与
``report_generator._get_config`` 一致：

===========================  ====================================================
key                          含义
===========================  ====================================================
auto_weekly_enabled          是否自动生成周报（True/False）
auto_weekly_weekday          周报生成日（0=周一 … 6=周日，默认 0）
auto_weekly_hour             周报生成整点小时（0-23，默认 8）
auto_monthly_enabled         是否自动生成月报（True/False）
auto_monthly_day             月报生成日（1-28，默认 1，避免月末 29/30/31 不存在）
auto_monthly_hour            月报生成整点小时（0-23，默认 8）
===========================  ====================================================

默认值偏向「周一早上看到上周周报」——一个人的 SOC 场景下，周五下班前拿到
周报比周一早上更实用，但周五下午生成会撞上写周报的时间点（用户自己在写），
所以默认放周一 08:00，admin 可改。

时区
----
用**服务器本地时间**判定「今天周几 / 几号 / 几点了」——运维心智里
「周一早上 8 点」就是本地时间。报告窗口本身仍由 report_generator 用 UTC 计算，
两者互不干扰。
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from app.core.config import settings
from app.core.database import SessionLocal

logger = logging.getLogger(__name__)

_task = None
_FIRST_RUN_DELAY = 180  # 启动后稍等，避免与其他后台任务挤在同一时刻

# 触发方标识，落进 SecurityReport.triggered_by
TRIGGERED_BY = "system:scheduler"


# ---------------------------------------------------------------------------
# 周期 key（幂等基石）
# ---------------------------------------------------------------------------

def weekly_period_key(now: datetime) -> str:
    """周报的周期标识，形如 ``2026-W42``（ISO 8601 周）。

    ISO 周的好处：跨年时归属唯一（2026-01-01 可能属于 2025-W53），
    不会出现「12/29 和 01/04 属于同一周但 key 不同」的重复。
    """
    iso = now.isocalendar()
    return f"{iso[0]}-W{iso[1]:02d}"


def monthly_period_key(now: datetime) -> str:
    """月报的周期标识，形如 ``2026-11``。"""
    return f"{now.year}-{now.month:02d}"


def period_key(report_type: str, now: datetime) -> str:
    if report_type == "weekly":
        return weekly_period_key(now)
    if report_type == "monthly":
        return monthly_period_key(now)
    raise ValueError(f"不支持自动生成的 report_type: {report_type}")


# ---------------------------------------------------------------------------
# 规则读取
# ---------------------------------------------------------------------------

def _get_bool_config(db, key: str, default: bool) -> bool:
    """读 soc_system_config(category='reports', key=...)；缺则回退默认。

    ★ 不能直接用 report_generator._get_config(db, key, True)：
    它做的是 ``type(default)(row.value)``，而 ``bool("false") is True``
    （非空字符串恒真）——写 "false" 会被当成 True，开关就关不掉。

    所以这里自己查原始字符串再解析。值接受
    "true"/"1"/"yes"/"on" 为真，"false"/"0"/"no"/"off" 为假，
    其它一律回退默认（避免手滑写错导致整条链路停摆）。
    """
    from app.models.system_config import SystemConfig

    row = db.query(SystemConfig).filter(
        SystemConfig.category == "reports", SystemConfig.key == key
    ).first()
    if row is None or row.value is None:
        return default
    text = str(row.value).strip().lower()
    if text in ("true", "1", "yes", "y", "on"):
        return True
    if text in ("false", "0", "no", "n", "off"):
        return False
    return default


def _get_int_config(db, key: str, default: int) -> int:
    from app.services.report_generator import _get_config

    raw = _get_config(db, key, default)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# 到期判定
# ---------------------------------------------------------------------------

def is_due(db, report_type: str, now: datetime) -> bool:
    """该 report_type 在 now 这个时刻是否到期（应生成）。

    判定条件（全部满足）：
      1. 该类型开启了自动生成
      2. 今天是该类型的生成日（周报按星期，月报按几号）
      3. 当前已过生成时刻（整点小时）
      4. 该周期尚未生成过（幂等）
    """
    if report_type == "weekly":
        if not _get_bool_config(db, "auto_weekly_enabled", True):
            return False
        weekday = _get_int_config(
            db, "auto_weekly_weekday", settings.REPORT_SCHEDULER_WEEKLY_WEEKDAY
        )
        hour = _get_int_config(
            db, "auto_weekly_hour", settings.REPORT_SCHEDULER_WEEKLY_HOUR
        )
        if now.weekday() != weekday:  # weekday(): 0=周一 … 6=周日（与 Python 惯例一致）
            return False
    elif report_type == "monthly":
        if not _get_bool_config(db, "auto_monthly_enabled", True):
            return False
        day = _get_int_config(
            db, "auto_monthly_day", settings.REPORT_SCHEDULER_MONTHLY_DAY
        )
        hour = _get_int_config(
            db, "auto_monthly_hour", settings.REPORT_SCHEDULER_MONTHLY_HOUR
        )
        # 防御：配置写成 29/30/31 而当月没那么多天时，回退到当月最后一天
        last_day = _last_day_of_month(now)
        target_day = min(day, last_day)
        if now.day != target_day:
            return False
    else:
        return False

    if now.hour < hour:
        return False

    # 幂等：该周期已有报告就不再生成
    if _period_already_generated(db, report_type, now):
        logger.info(
            "report scheduler: %s %s 已生成过，跳过",
            report_type, period_key(report_type, now),
        )
        return False
    return True


def _last_day_of_month(now: datetime) -> int:
    if now.month == 12:
        nxt = now.replace(year=now.year + 1, month=1, day=1)
    else:
        nxt = now.replace(month=now.month + 1, day=1)
    return (nxt - timedelta(days=1)).day


def _period_already_generated(db, report_type: str, now: datetime) -> bool:
    """该周期是否已经生成过报告。

    判据：同一 report_type 下，窗口起点落在同一周期内的报告已存在。
    weekly 的窗口是「过去 7 天」，跨周时窗口起点会落在上一周——
    所以不能用 period_start 直接比，要用「报告窗口所属周期」来判断。
    为避免这种边界歧义，这里改用更稳的判据：
    **同一 report_type 且窗口结束时间在当前周期内的报告已存在 → 跳过。**
    即：今天的周报如果今天早些时候已经出过了（无论窗口怎么算），就不再出。
    """
    from sqlalchemy import select

    from app.models.security_report import SecurityReport

    key = period_key(report_type, now)
    rows = db.execute(
        select(SecurityReport).where(SecurityReport.report_type == report_type)
    ).scalars().all()
    for r in rows:
        # 报告窗口结束时间（period_end）落在当前周期内 → 视为本期已出
        end = r.period_end
        if end is None:
            continue
        if report_type == "weekly":
            if weekly_period_key(end) == key:
                return True
        else:
            if monthly_period_key(end) == key:
                return True
    return False


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------

def _generate_one(db, report_type: str, now: datetime) -> Optional[dict]:
    """生成一份报告；返回摘要信息（失败返回 None，不抛给调度循环）。"""
    from app.services.report_generator import SecurityReportService

    try:
        svc = SecurityReportService(db)
        report = svc.generate(
            report_type=report_type,
            triggered_by=TRIGGERED_BY,
            force_glm=True,
        )
    except Exception as exc:  # noqa: BLE001 — 报告生成失败不该拖垮调度器
        logger.exception("report scheduler: 生成 %s 报告失败: %s", report_type, exc)
        return None

    degraded = (report.data_coverage or {}).get("data_degraded", False)
    ai_source = (report.data_coverage or {}).get("ai_source")
    logger.info(
        "report scheduler: %s 报告已生成 id=%s title=%s ai_source=%s degraded=%s",
        report_type, report.id, report.title, ai_source, degraded,
    )
    return {
        "report_type": report_type,
        "report_id": str(report.id),
        "title": report.title,
        "period_key": period_key(report_type, now),
        "ai_source": ai_source,
        "data_degraded": degraded,
    }


def run_report_once(now: Optional[datetime] = None) -> dict:
    """执行一轮：检查 weekly / monthly 是否到期，到期则生成。

    返回 {"weekly": {...}|None, "monthly": {...}|None}。
    供调度循环与手动触发端点共用。
    """
    from datetime import timezone as _tz

    if now is None:
        now = datetime.now()  # 本地时间：判定「今天周几/几号/几点」用本地更符合运维心智

    result = {"weekly": None, "monthly": None}
    db = SessionLocal()
    try:
        for report_type in ("weekly", "monthly"):
            if not is_due(db, report_type, now):
                continue
            info = _generate_one(db, report_type, now)
            if info:
                result[report_type] = info
    finally:
        db.close()
    return result


# ---------------------------------------------------------------------------
# 调度循环
# ---------------------------------------------------------------------------

def _seconds_until_next_check(now: datetime) -> float:
    """计算到下一个整点巡检时刻的秒数（本地时间）。

    每天每小时检查一次即可——「今天该出周报」是按天判定的，分钟级精度没有意义。
    """
    target = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    return (target - now).total_seconds()


async def _loop() -> None:
    logger.info(
        "report scheduler loop started, weekly_day=%s weekly_hour=%s "
        "monthly_day=%s monthly_hour=%s",
        settings.REPORT_SCHEDULER_WEEKLY_WEEKDAY,
        settings.REPORT_SCHEDULER_WEEKLY_HOUR,
        settings.REPORT_SCHEDULER_MONTHLY_DAY,
        settings.REPORT_SCHEDULER_MONTHLY_HOUR,
    )
    await asyncio.sleep(_FIRST_RUN_DELAY)
    while True:
        try:
            now = datetime.now()
            delay = _seconds_until_next_check(now)
            logger.info("report scheduler: next check in %.0fs", delay)
            await asyncio.sleep(delay)

            result = run_report_once()
            if any(result.values()):
                logger.info("report scheduler round: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("report scheduler iteration failed")
            await asyncio.sleep(3600)  # 出错后 1h 再试，避免空转


def start_report_scheduler() -> None:
    """启动后台报告生成任务（幂等）。"""
    global _task
    if not settings.REPORT_SCHEDULER_ENABLED:
        logger.info("report scheduler disabled by config (REPORT_SCHEDULER_ENABLED=False)")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("report scheduler task started")


def stop_report_scheduler() -> None:
    """停止后台报告生成任务。"""
    global _task
    if _task is not None:
        _task.cancel()
        _task = None
    logger.info("report scheduler stopped")
