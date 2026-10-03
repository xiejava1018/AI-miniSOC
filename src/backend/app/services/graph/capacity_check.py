"""图谱扩容触发线（OH-3.8）

职责：
  - 周期巡检（默认 5 分钟）：读取 ``configs/graph_capacity.yaml`` 阈值
  - 边数 >= edges_threshold 或 任一 query_type 的 P95 >= p95_threshold_ms → 触发告警
  - 告警行为：
      1. 写 audit_log（hash 链永久存证）
      2. 给所有 admin 用户推 SOC Notification（落库 + WS 推送）
      3. （预留）钉钉 webhook：当前项目无独立钉钉通道；后续如有只需在 ``notify_admin`` 内加 POST

设计依据：
  - docs/design/2026-09-30-资产管理AI能力建设-实施方案.md OH-3.8
  - docs/design/2026-10-03-资产管理AI能力建设-任务进度跟踪.md §三 OH-3.8

边界（不要做的事）：
  - **不**做实时增量采集（slow_query_monitor 已经做 P95 实时告警；本服务是扩容级宏观告警）
  - **不**直接操作图谱或清理数据（只读 + 通知）
  - **不**替代容量调度/限流（那是 OH-4.x 范围）
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from sqlalchemy import text

from app.core.database import SessionLocal
from app.services.graph.perf import snapshot as perf_snapshot

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------

CONFIG_PATH = Path(__file__).resolve().parents[5] / "configs" / "graph_capacity.yaml"


@dataclass
class CapacityConfig:
    enabled: bool
    interval_seconds: int
    cooldown_seconds: int
    edges_threshold: int
    p95_threshold_ms: float
    notify_role_codes: List[str]
    notification_type: str
    notification_link: str

    @classmethod
    def from_dict(cls, d: dict) -> "CapacityConfig":
        return cls(
            enabled=bool(d.get("enabled", True)),
            interval_seconds=max(int(d.get("interval_seconds", 300)), 30),
            cooldown_seconds=int(d.get("cooldown_seconds", 1800)),
            edges_threshold=int(d.get("edges_threshold", 10000)),
            p95_threshold_ms=float(d.get("p95_threshold_ms", 500.0)),
            notify_role_codes=list(d.get("notify_role_codes", ["admin"])),
            notification_type=str(d.get("notification_type", "graph_capacity_alert")),
            notification_link=str(
                d.get("notification_link", "/#/asset/graph/perf-dashboard/index")
            ),
        )


def load_config() -> CapacityConfig:
    """读取 yaml；缺失或解析失败 → 用默认值（避免启动失败）。"""
    try:
        if not CONFIG_PATH.exists():
            logger.warning("graph_capacity.yaml 不存在 (%s)，使用默认阈值", CONFIG_PATH)
            return CapacityConfig.from_dict({})
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return CapacityConfig.from_dict(data)
    except Exception:  # noqa: BLE001
        logger.exception("graph_capacity.yaml 解析失败，使用默认阈值")
        return CapacityConfig.from_dict({})


# ---------------------------------------------------------------------------
# 容量探测
# ---------------------------------------------------------------------------

def probe_capacity(db=None) -> dict:
    """读取当前图谱规模 + P95 滑窗。

    Returns:
        {
          "edges_total": int,
          "nodes_total": int,
          "p95_by_query_type": {neighbors: float, paths: float, ...},
          "samples_by_query_type": {neighbors: int, ...},
          "probe_at": iso8601 str,
        }
    """
    _own = db is None
    if _own:
        db = SessionLocal()
    try:
        edges_total = (
            db.execute(text("SELECT count(*) FROM soc_graph_edges")).scalar() or 0
        )
        nodes_total = (
            db.execute(text("SELECT count(*) FROM soc_graph_nodes")).scalar() or 0
        )
        snap = perf_snapshot()
        return {
            "edges_total": int(edges_total),
            "nodes_total": int(nodes_total),
            "p95_by_query_type": dict(snap.get("p95_ms", {})),
            "samples_by_query_type": dict(snap.get("samples", {})),
            "probe_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if _own:
            db.close()


# ---------------------------------------------------------------------------
# 阈值评估
# ---------------------------------------------------------------------------

def evaluate_thresholds(probe: dict, cfg: CapacityConfig) -> Dict[str, dict]:
    """对照阈值评估，返回每条触发原因 + 数值。

    Returns:
        {
          "edges": {"triggered": bool, "current": int, "threshold": int, "delta_pct": float},
          "p95_<qt>": {"triggered": bool, "current": float, "threshold": float, ...},
        }
    """
    out: Dict[str, dict] = {}

    # 边数
    edges = int(probe.get("edges_total", 0))
    delta_pct = (
        ((edges - cfg.edges_threshold) / cfg.edges_threshold * 100.0)
        if cfg.edges_threshold > 0
        else 0.0
    )
    out["edges"] = {
        "triggered": edges >= cfg.edges_threshold,
        "current": edges,
        "threshold": cfg.edges_threshold,
        "delta_pct": round(delta_pct, 2),
    }

    # P95（每个 query_type 单独评估）
    for qt, p95 in (probe.get("p95_by_query_type") or {}).items():
        p95_f = float(p95 or 0.0)
        out[f"p95_{qt}"] = {
            "triggered": p95_f >= cfg.p95_threshold_ms,
            "current": p95_f,
            "threshold": cfg.p95_threshold_ms,
            "query_type": qt,
        }

    return out


def build_alert_message(evaluations: Dict[str, dict]) -> Optional[str]:
    """根据评估结果构造可读告警消息。无触发返回 None。"""
    reasons: List[str] = []
    edges_eval = evaluations.get("edges", {})
    if edges_eval.get("triggered"):
        reasons.append(
            f"边数 {edges_eval['current']:,} ≥ 阈值 {edges_eval['threshold']:,} "
            f"(+{edges_eval['delta_pct']:.1f}%)"
        )
    for key, ev in evaluations.items():
        if key == "edges":
            continue
        if not ev.get("triggered"):
            continue
        reasons.append(
            f"P95[{ev['query_type']}] {ev['current']:.1f}ms ≥ 阈值 {ev['threshold']:.0f}ms"
        )
    if not reasons:
        return None
    return "图谱扩容触发线触发: " + "; ".join(reasons)


# ---------------------------------------------------------------------------
# 告警落地（审计 + 通知）
# ---------------------------------------------------------------------------

async def notify_admin(cfg: CapacityConfig, title: str, content: str) -> int:
    """给所有 admin 角色用户推 SOC Notification（落库 + WS）。

    Returns:
        推送成功的用户数
    """
    try:
        from app.services.notification_service import NotificationService
        from app.models import User, Role
        from app.core.database import SessionLocal as _SL
    except Exception:  # noqa: BLE001
        logger.exception("通知依赖导入失败")
        return 0

    sent = 0
    db = _SL()
    try:
        # 取所有角色 code ∈ notify_role_codes 的用户
        rows = (
            db.query(User)
            .join(Role, User.role_id == Role.id)
            .filter(Role.code.in_(cfg.notify_role_codes))
            .all()
        )
        target_ids = [
            u.id for u in rows if getattr(u, "status", "active") == "active"
        ]
        if not target_ids:
            logger.warning(
                "capacity alert: 无目标用户 (role_codes=%s)", cfg.notify_role_codes
            )
            return 0
        svc = NotificationService(db)
        for uid in target_ids:
            try:
                await svc.create(
                    user_id=uid,
                    type=cfg.notification_type,
                    title=title,
                    content=content,
                    link=cfg.notification_link,
                    push_ws=True,
                )
                sent += 1
            except Exception:  # noqa: BLE001
                logger.exception("capacity alert notify failed user_id=%s", uid)
    finally:
        db.close()
    return sent


def write_audit_log(evaluations: dict, message: str) -> None:
    """写 audit log（hash 链存证）。

    失败不抛异常（不阻塞告警主流程）。
    """
    try:
        from app.services.audit_log_service import AuditLogService
        from app.core.database import SessionLocal as _SL

        db = _SL()
        try:
            svc = AuditLogService(db)
            svc.create_audit_log(
                user_id=None,
                username="system",
                action="graph_capacity_alert",
                resource_type="graph_capacity",
                resource_name="capacity_check",
                new_values={
                    "message": message,
                    "evaluations": evaluations,
                },
                status="success",
            )
            db.commit()
        finally:
            db.close()
    except Exception:  # noqa: BLE001
        logger.exception("capacity alert audit log 写入失败")


# ---------------------------------------------------------------------------
# 冷却（防抖）
# ---------------------------------------------------------------------------

_last_trigger_at: Dict[str, float] = {}  # key: "edges" | "p95_<qt>" → monotonic ts


def _should_trigger(key: str, cfg: CapacityConfig) -> bool:
    import time as _time
    now = _time.monotonic()
    last = _last_trigger_at.get(key)
    if last is None or (now - last) >= cfg.cooldown_seconds:
        _last_trigger_at[key] = now
        return True
    return False


def _schedule_notify(cfg: CapacityConfig, message: str) -> None:
    """在已有 event loop 中 fire-and-forget 推通知；无 loop 时直接 asyncio.run。

    失败不抛（以不阻塞主流程为优先）。
    """
    async def _safe_run():
        try:
            await notify_admin(cfg, "图谱扩容告警", message)
        except Exception:  # noqa: BLE001
            logger.exception("capacity alert notify task crashed")

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_safe_run())
        else:
            loop.run_until_complete(_safe_run())
    except RuntimeError:
        try:
            asyncio.run(_safe_run())
        except Exception:  # noqa: BLE001
            logger.exception("capacity alert notify (sync fallback) crashed")


def evaluate_once(db=None, *, emit: bool = True) -> dict:
    """执行一轮容量巡检（同步可单测）。

    Args:
        db: 可注入 session（测试用）；默认开 SessionLocal。
        emit: True=触发时写 audit + 推通知；False=只评估不触发（端点排障/测试用）。
    """
    cfg = load_config()
    probe = probe_capacity(db)
    evaluations = evaluate_thresholds(probe, cfg)
    message = build_alert_message(evaluations)

    triggered_keys: List[str] = []
    if message and emit:
        for key, ev in evaluations.items():
            if ev.get("triggered") and _should_trigger(key, cfg):
                triggered_keys.append(key)
        # 写审计
        write_audit_log(evaluations, message)
        # 推通知（fire-and-forget）
        _schedule_notify(cfg, message)

    return {
        "triggered": triggered_keys,
        "message": message,
        "probe": probe,
        "evaluations": evaluations,
        "thresholds": {
            "edges_threshold": cfg.edges_threshold,
            "p95_threshold_ms": cfg.p95_threshold_ms,
        },
    }


# ---------------------------------------------------------------------------
# 后台循环（与 slow_query_monitor 风格一致）
# ---------------------------------------------------------------------------

_task: Optional[asyncio.Task] = None
_FIRST_RUN_DELAY = 5  # 启动后 5s 跑首轮，给上游 builder / monitor 暖机


async def _loop() -> None:
    cfg = load_config()
    interval = max(cfg.interval_seconds, 30)
    logger.info("graph capacity check started, interval=%ds", interval)
    await asyncio.sleep(_FIRST_RUN_DELAY)
    while True:
        try:
            result = await asyncio.to_thread(evaluate_once)
            if result["triggered"]:
                logger.warning(
                    "graph capacity check triggered: %s", result["message"]
                )
        except Exception:  # noqa: BLE001
            logger.exception("graph capacity check round failed")
        await asyncio.sleep(interval)


def start_graph_capacity_check() -> None:
    global _task
    cfg = load_config()
    if not cfg.enabled:
        logger.info("graph capacity check disabled by config")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop())


async def stop_graph_capacity_check() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        _task = None
        logger.info("graph capacity check stopped")
