"""资产对账服务（P3 / F1.3）

对比台账（soc_assets）与实际网络（Wazuh Agent 列表），产出三类差异：
  shadow    Wazuh 有 Agent，台账没有        → 建议补录
  offline   台账有，Wazuh 侧断开/Agent 已删 → 建议确认下线
  mismatch  Agent 与台账信息不一致          → 建议修正

设计约束（均来自 PRD F1.3，不是可选项）：
  1. 判定全部由规则完成，不经过 LLM。AI 只负责把差异"讲成人话"（见 reconcile_ai.py）。
  2. 必须标注数据新鲜度。源不健康时页面要横幅告警，
     **禁止在数据不新鲜时静默给出"无差异"结论**——那比报错更危险。
  3. 处理动作走状态机，重复处理第二个请求必须失败，且不引入额外锁。
  4. 全部处理动作落 soc_audit_logs。
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_reconciliation import (
    STATUS_PENDING,
    TERMINAL_STATUSES,
    TYPE_MISMATCH,
    TYPE_OFFLINE,
    TYPE_SHADOW,
    AssetReconciliation,
)
from app.models.audit_log import AuditLog
from app.models.scanner_models import ScanFinding
from app.models.source_health import SourceHealth
from app.models.sync_dead_letter import SyncDeadLetter
from app.models.sync_task import SyncTask

logger = logging.getLogger(__name__)

# Wazuh manager 自身的 agent id。它的 ip 恒为 127.0.0.1、lastKeepAlive 恒为
# 9999-12-31（哨兵值），拿它跟台账比对只会制造噪声，故默认排除。
MANAGER_AGENT_ID = "000"

# lastKeepAlive 的哨兵年份，见上
_SENTINEL_YEAR = 9999

# 断开超过这么久才算"疑似下线"。低于此阈值可能只是临时重启/网络抖动，
# 报出来会让运维疲劳（PRD 举例用的就是 7 天）。
OFFLINE_DAYS_THRESHOLD = 7

# 台账侧数据超过这么久没同步，就认为不新鲜，结论要加"可能不全"的警示
STALE_SYNC_HOURS = 24

# 参与 mismatch 比对的字段：台账列名 -> (人类可读名, 从 agent 取值的函数)
_COMPARE_FIELDS: dict[str, tuple[str, Any]] = {
    "asset_ip": ("IP 地址", lambda ag: ag.get("ip")),
    "name": ("主机名", lambda ag: ag.get("name")),
    "os_name": ("操作系统", lambda ag: (ag.get("os") or {}).get("name")),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_ts(value: Any) -> Optional[datetime]:
    """宽容解析 Wazuh 的时间戳；无法解析或为哨兵值时返回 None。"""
    if not value:
        return None
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return None
    if dt.year >= _SENTINEL_YEAR:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _norm(value: Any) -> str:
    """比对用的归一化：去空白、转小写。避免 'Ubuntu ' vs 'ubuntu' 的假差异。"""
    return str(value or "").strip().lower()


@dataclass
class Freshness:
    """数据新鲜度快照，会原样写进每条差异的 details，使结论可追溯。"""

    checked_at: datetime
    wazuh_reachable: bool
    wazuh_error: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = None
    sync_stale: bool = False
    unhealthy_sources: list[dict] = field(default_factory=list)
    dead_letter_pending: int = 0

    @property
    def degraded(self) -> bool:
        """任一维度不可信 → 前端顶部横幅提示"源异常中，结果可能不全"。"""
        return (
            not self.wazuh_reachable
            or self.sync_stale
            or bool(self.unhealthy_sources)
            or self.dead_letter_pending > 0
        )

    def to_dict(self) -> dict:
        return {
            "checked_at": self.checked_at.isoformat(),
            "wazuh_reachable": self.wazuh_reachable,
            "wazuh_error": self.wazuh_error,
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_sync_status": self.last_sync_status,
            "sync_stale": self.sync_stale,
            "unhealthy_sources": self.unhealthy_sources,
            "dead_letter_pending": self.dead_letter_pending,
            "degraded": self.degraded,
        }


class ReconciliationError(RuntimeError):
    """对账无法完成（如 Wazuh 不可达）。调用方应把它当失败上报，而不是当"无差异"。"""


class AssetReconciliationService:
    def __init__(self, db: Session):
        self.db = db

    # ------------------------------------------------------------------ 新鲜度

    def collect_freshness(
        self, wazuh_reachable: bool = True, wazuh_error: Optional[str] = None
    ) -> Freshness:
        """汇总三层数据健康，作为本次对账的可信度依据。"""
        fr = Freshness(
            checked_at=_utcnow(),
            wazuh_reachable=wazuh_reachable,
            wazuh_error=wazuh_error,
        )

        last_task = self.db.execute(
            select(SyncTask)
            .where(SyncTask.status == "completed")
            .order_by(SyncTask.completed_at.desc().nullslast(), SyncTask.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()
        if last_task is not None:
            fr.last_sync_at = last_task.completed_at or last_task.created_at
            fr.last_sync_status = last_task.status
        if fr.last_sync_at is not None:
            fr.sync_stale = fr.last_sync_at < _utcnow() - timedelta(hours=STALE_SYNC_HOURS)
        else:
            # 从未成功同步过：这本身就是不新鲜，必须显式标注而非当作"正常"
            fr.sync_stale = True

        # 只检查稽核实际依赖的数据源（2026-08-28 修正）：
        # 资产稽核的输入 = Wazuh agent 列表 + soc_assets 台账 + scanner findings，
        # 台账的写入方 = wazuh/tplink/scanner 三类采集器。
        # loki:browsing_detection（上网行为）与 opensearch:vuln（漏洞状态）
        # 不是稽核输入——它们过期不该降级稽核结论的可信度。
        # 此前遍历全部 SourceHealth 行，导致 loki 检测停用时稽核页长期显示
        # "源异常，结果可能不全"，属语义误判（用户反馈）。
        _RECON_RELEVANT_SOURCES = {
            "wazuh:agents",       # Wazuh API + agent 同步
            "tplink:collector",   # 台账写入方（路由器资产）
            "scanner:discovery",  # 台账/发现写入方（资产发现）
            "scanner:ports",      # 台账写入方（端口扫描）
        }
        for sh in self.db.execute(select(SourceHealth)).scalars():
            if sh.source_key not in _RECON_RELEVANT_SOURCES:
                continue
            interval = sh.expected_interval_seconds
            overdue = False
            if interval and sh.last_success_at:
                overdue = sh.last_success_at < _utcnow() - timedelta(seconds=interval * 3)
            failing = bool(
                sh.last_failure_at
                and (not sh.last_success_at or sh.last_failure_at > sh.last_success_at)
            )
            if overdue or failing:
                fr.unhealthy_sources.append(
                    {
                        "source_key": sh.source_key,
                        "source_type": sh.source_type,
                        "reason": "overdue" if overdue else "last_run_failed",
                        "last_success_at": sh.last_success_at.isoformat()
                        if sh.last_success_at
                        else None,
                        "last_failure_message": (sh.last_failure_message or "")[:200] or None,
                    }
                )

        fr.dead_letter_pending = (
            self.db.execute(
                select(func.count())
                .select_from(SyncDeadLetter)
                .where(SyncDeadLetter.resolved.is_(False))
            ).scalar()
            or 0
        )
        return fr

    # ------------------------------------------------------------------ 对账

    def run(
        self,
        agents: Optional[list[dict]] = None,
        task_id: Optional[uuid.UUID] = None,
        include_manager: bool = False,
    ) -> dict:
        """执行一次对账，落库差异，返回本次批次摘要。

        agents 传 None 时实时调 Wazuh API。Wazuh 不可达直接抛
        ReconciliationError——绝不退化成"无差异"。
        """
        wazuh_error: Optional[str] = None
        if agents is None:
            try:
                from app.services.wazuh_client import WazuhClient

                client = WazuhClient()
                try:
                    agents = client.get_agents()
                finally:
                    client.close()
            except Exception as exc:  # noqa: BLE001 — 任何异常都要转成明确的对账失败
                wazuh_error = f"{type(exc).__name__}: {exc}"[:500]
                logger.warning("对账失败：Wazuh 不可达 %s", wazuh_error)
                raise ReconciliationError(
                    f"Wazuh API 不可达，本次对账终止（{wazuh_error}）。"
                    "请先恢复数据源，避免把采集故障误判为资产差异。"
                ) from exc

        if not include_manager:
            agents = [a for a in agents if str(a.get("id")) != MANAGER_AGENT_ID]

        freshness = self.collect_freshness(wazuh_reachable=True, wazuh_error=wazuh_error)
        fr_snapshot = freshness.to_dict()
        run_id = uuid.uuid4()
        now = _utcnow()

        assets: list[Asset] = list(self.db.execute(select(Asset)).scalars())
        by_agent_id = {
            str(a.wazuh_agent_id): a for a in assets if a.wazuh_agent_id not in (None, "")
        }
        by_ip: dict[str, Asset] = {}
        for a in assets:
            if a.asset_ip:
                by_ip.setdefault(str(a.asset_ip).strip(), a)

        rows: list[AssetReconciliation] = []
        matched_agent_ids: set[str] = set()

        # ---- 遍历 Wazuh 侧：找影子资产与信息不一致
        for ag in agents:
            agent_id = str(ag.get("id") or "")
            agent_ip = str(ag.get("ip") or "").strip()
            asset = by_agent_id.get(agent_id)
            linked_by = "wazuh_agent_id"

            if asset is None and agent_ip:
                # agent_id 对不上，再用 IP 兜一次：同一台机器只是没记 agent_id，
                # 这属于"信息不一致"，报成影子资产会造成重复补录。
                asset = by_ip.get(agent_ip)
                linked_by = "asset_ip"

            if asset is None:
                rows.append(
                    AssetReconciliation(
                        run_id=run_id,
                        task_id=task_id,
                        asset_id=None,
                        reconciliation_type=TYPE_SHADOW,
                        details={
                            "freshness": fr_snapshot,
                            "agent": self._agent_brief(ag),
                            "suggestion": "确认后补录台账",
                        },
                        status=STATUS_PENDING,
                        created_at=now,
                    )
                )
                continue

            matched_agent_ids.add(agent_id)
            diffs = self._field_diffs(asset, ag)
            if linked_by == "asset_ip":
                diffs.append(
                    {
                        "field": "wazuh_agent_id",
                        "label": "Wazuh Agent 关联",
                        "ledger_value": asset.wazuh_agent_id,
                        "actual_value": agent_id,
                    }
                )
            if diffs:
                rows.append(
                    AssetReconciliation(
                        run_id=run_id,
                        task_id=task_id,
                        asset_id=asset.id,
                        reconciliation_type=TYPE_MISMATCH,
                        details={
                            "freshness": fr_snapshot,
                            "agent": self._agent_brief(ag),
                            "linked_by": linked_by,
                            "diffs": diffs,
                            "suggestion": "核对后修正台账信息",
                        },
                        status=STATUS_PENDING,
                        created_at=now,
                    )
                )

        # ---- 遍历台账侧：找疑似下线
        agent_by_id = {str(a.get("id")): a for a in agents}
        for asset in assets:
            aid = str(asset.wazuh_agent_id or "")
            if not aid:
                # 台账里压根没关联 Wazuh 的资产（如路由器采集来的）不参与下线判定，
                # 否则 51 台非 Agent 资产会全被误报下线。
                continue
            ag = agent_by_id.get(aid)
            if ag is None:
                rows.append(
                    AssetReconciliation(
                        run_id=run_id,
                        task_id=task_id,
                        asset_id=asset.id,
                        reconciliation_type=TYPE_OFFLINE,
                        details={
                            "freshness": fr_snapshot,
                            "reason": "agent_deleted",
                            "ledger": self._asset_brief(asset),
                            "suggestion": "Wazuh 中已无此 Agent，确认是否已退役",
                        },
                        status=STATUS_PENDING,
                        created_at=now,
                    )
                )
                continue

            if ag.get("status") == "active":
                continue
            last_keep_alive = _parse_ts(ag.get("lastKeepAlive"))
            days = (
                round((_utcnow() - last_keep_alive).total_seconds() / 86400, 1)
                if last_keep_alive
                else None
            )
            if days is not None and days < OFFLINE_DAYS_THRESHOLD:
                # 断开时间还短，可能只是重启，不报
                continue
            rows.append(
                AssetReconciliation(
                    run_id=run_id,
                    task_id=task_id,
                    asset_id=asset.id,
                    reconciliation_type=TYPE_OFFLINE,
                    details={
                        "freshness": fr_snapshot,
                        "reason": "agent_disconnected",
                        "agent_status": ag.get("status"),
                        "last_keep_alive": last_keep_alive.isoformat()
                        if last_keep_alive
                        else None,
                        "disconnected_days": days,
                        "ledger": self._asset_brief(asset),
                        "agent": self._agent_brief(ag),
                        "suggestion": f"已断开 {days} 天，确认是否已退役"
                        if days is not None
                        else "Agent 未连接，确认是否已退役",
                    },
                    status=STATUS_PENDING,
                    created_at=now,
                )
            )

        for r in rows:
            self.db.add(r)

        # ---- P3/F-S1 扫描器发现 → 影子资产（final.md §9.1）
        scanner_shadow_count = self.reconcile_scanner_findings(
            run_id=run_id, task_id=task_id, lookback_hours=24,
        )
        # scanner shadow 另计（不走 Wazuh 主路）
        self.db.commit()

        summary = {
            "run_id": str(run_id),
            "checked_at": now.isoformat(),
            "agent_count": len(agents),
            "asset_count": len(assets),
            "linked_count": len(matched_agent_ids),
            "diff_total": len(rows) + scanner_shadow_count,
            "by_type": {
                TYPE_SHADOW: sum(1 for r in rows if r.reconciliation_type == TYPE_SHADOW) + scanner_shadow_count,
                TYPE_OFFLINE: sum(1 for r in rows if r.reconciliation_type == TYPE_OFFLINE),
                TYPE_MISMATCH: sum(1 for r in rows if r.reconciliation_type == TYPE_MISMATCH),
            },
            "scanner_shadow_count": scanner_shadow_count,
            "freshness": fr_snapshot,
        }
        logger.info(
            "对账完成 run_id=%s agents=%d assets=%d diffs=%d degraded=%s",
            run_id,
            len(agents),
            len(assets),
            len(rows),
            freshness.degraded,
        )
        return summary

    def reconcile_scanner_findings(
        self,
        run_id: uuid.UUID,
        task_id: Optional[uuid.UUID] = None,
        lookback_hours: int = 24,
    ) -> int:
        """扫描器发现 → 影子资产补齐（final.md §9.1 扩展点）。

        遍历 ``soc_scan_findings``（finding_status in ('new', 'known')），
        产 ``AssetReconciliation(type=TYPE_SHADOW, asset_id=None)``。
        关键不变量（ADR-6）：
          - matched_asset_id 非空的 finding → IP 已在台账，不产 shadow（F1.3 跳过）
          - finding_status in ('adopted', 'ignored') → 已处置，不重复产
          - 按 ``(asset_ip, run_id)`` 去重：避免每轮重复产同一条 shadow（R7 修正）
          - 最近 24h 不重复产同 IP 的 shadow（lookback_hours 参数）
        返回：本次新增的 shadow 行数。
        """
        lookback_cutoff = _utcnow() - timedelta(hours=lookback_hours)
        # 先查最近一批 (run_id, asset_ip) 的 pending shadow（避免每轮重复产）
        recent_shadows = (
            self.db.query(AssetReconciliation)
            .filter(
                AssetReconciliation.reconciliation_type == TYPE_SHADOW,
                AssetReconciliation.status == STATUS_PENDING,
                AssetReconciliation.created_at >= lookback_cutoff,
            )
            .all()
        )
        recent_ips = {str((r.details or {}).get("asset_ip", "")).strip() for r in recent_shadows}
        recent_ips.discard("")

        findings = (
            self.db.query(ScanFinding)
            .filter(ScanFinding.finding_status.in_(("new", "known")))
            .all()
        )

        new_rows: list[AssetReconciliation] = []
        for f in findings:
            ip = (f.asset_ip or "").strip()
            if not ip or ip in recent_ips:
                continue
            # matched_asset_id 非空 → IP 已在台账，不产 shadow
            if f.matched_asset_id:
                # 同步状态：new → known（让前端展示一致）—— 仅内存修改，不 commit
                if f.finding_status == "new":
                    f.finding_status = "known"
                continue
            # status=="known"但 matched_asset_id 为空：可能是历史脏数据/异常，
            # 产 shadow 让运维通过「一键纳管」/「忽略」处置（不入死信）
            new_rows.append(
                AssetReconciliation(
                    run_id=run_id,
                    task_id=task_id,
                    asset_id=None,    # 资产不在台账
                    reconciliation_type=TYPE_SHADOW,
                    details={
                        "source": "scanner",                       # 标注来源（final.md §9.2 分支文案）
                        "scanner_id": f.scanner_id,
                        "asset_ip": ip,
                        "mac_address": f.mac_address,
                        "os_guess": f.os_guess,
                        "exposure": f.exposure,
                        "finding_id": f.id,                          # 便于 「一键纳管」反查
                        "scan_task_uuid": str(f.scan_task_uuid),
                        "suggestion": "内网扫描发现但未纳管，建议确认后一键纳管或标记忽略",
                    },
                    status=STATUS_PENDING,
                    created_at=_utcnow(),
                )
            )
            recent_ips.add(ip)  # 同一 IP 在本次 run 内也只产一次

        for r in new_rows:
            self.db.add(r)
        if new_rows:
            self.db.commit()
        if new_rows:
            logger.info(
                "scanner findings → shadow: %d new rows (run_id=%s, lookback=%dh)",
                len(new_rows), run_id, lookback_hours,
            )
        return len(new_rows)

    def _field_diffs(self, asset: Asset, agent: dict) -> list[dict]:
        diffs = []
        for col, (label, getter) in _COMPARE_FIELDS.items():
            actual = getter(agent)
            ledger = getattr(asset, col, None)
            # 任一侧缺失就不判差异：缺数据是数据质量问题，不是"不一致"，
            # 混在一起会把台账空字段刷成大量噪声差异。
            if not _norm(actual) or not _norm(ledger):
                continue
            if _norm(actual) != _norm(ledger):
                diffs.append(
                    {
                        "field": col,
                        "label": label,
                        "ledger_value": ledger,
                        "actual_value": actual,
                    }
                )
        return diffs

    @staticmethod
    def _agent_brief(agent: dict) -> dict:
        os_data = agent.get("os") or {}
        return {
            "id": agent.get("id"),
            "name": agent.get("name"),
            "ip": agent.get("ip"),
            "status": agent.get("status"),
            "os_name": os_data.get("name"),
            "os_version": os_data.get("version"),
            "os_platform": os_data.get("platform"),
            "version": agent.get("version"),
            "date_add": str(agent.get("dateAdd")) if agent.get("dateAdd") else None,
            "last_keep_alive": str(agent.get("lastKeepAlive"))
            if agent.get("lastKeepAlive")
            else None,
        }

    @staticmethod
    def _asset_brief(asset: Asset) -> dict:
        return {
            "id": str(asset.id),
            "name": asset.name,
            "asset_ip": asset.asset_ip,
            "asset_status": asset.asset_status,
            "os_name": asset.os_name,
            "wazuh_agent_id": asset.wazuh_agent_id,
            "data_source": asset.data_source,
            "last_synced_at": asset.last_synced_at.isoformat()
            if asset.last_synced_at
            else None,
        }

    # ------------------------------------------------------------------ 查询

    def latest_run_id(self) -> Optional[uuid.UUID]:
        return self.db.execute(
            select(AssetReconciliation.run_id)
            .order_by(AssetReconciliation.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def list_diffs(
        self,
        run_id: Optional[uuid.UUID] = None,
        recon_type: Optional[str] = None,
        status: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict:
        stmt = select(AssetReconciliation)
        if run_id is not None:
            stmt = stmt.where(AssetReconciliation.run_id == run_id)
        if recon_type:
            stmt = stmt.where(AssetReconciliation.reconciliation_type == recon_type)
        if status:
            stmt = stmt.where(AssetReconciliation.status == status)

        total = self.db.execute(
            select(func.count()).select_from(stmt.subquery())
        ).scalar() or 0
        rows = list(
            self.db.execute(
                stmt.order_by(AssetReconciliation.created_at.desc())
                .offset((max(page, 1) - 1) * page_size)
                .limit(page_size)
            ).scalars()
        )
        return {"total": total, "page": page, "page_size": page_size, "records": rows}

    def summary(self, run_id: Optional[uuid.UUID] = None) -> dict:
        """某批次（默认最近一次）的差异分布 + 新鲜度。"""
        rid = run_id or self.latest_run_id()
        if rid is None:
            return {
                "run_id": None,
                "has_data": False,
                "message": "尚未执行过对账",
                "by_type": {},
                "by_status": {},
                "pending_total": 0,
                "freshness": None,
            }

        by_type: dict[str, int] = {}
        for t, c in self.db.execute(
            select(AssetReconciliation.reconciliation_type, func.count())
            .where(AssetReconciliation.run_id == rid)
            .group_by(AssetReconciliation.reconciliation_type)
        ):
            by_type[t] = c
        by_status: dict[str, int] = {}
        for s, c in self.db.execute(
            select(AssetReconciliation.status, func.count())
            .where(AssetReconciliation.run_id == rid)
            .group_by(AssetReconciliation.status)
        ):
            by_status[s] = c

        first = self.db.execute(
            select(AssetReconciliation)
            .where(AssetReconciliation.run_id == rid)
            .limit(1)
        ).scalar_one_or_none()
        freshness = (first.details or {}).get("freshness") if first else None
        checked_at = first.created_at.isoformat() if first else None

        return {
            "run_id": str(rid),
            "has_data": True,
            "checked_at": checked_at,
            "by_type": by_type,
            "by_status": by_status,
            "diff_total": sum(by_type.values()),
            "pending_total": by_status.get(STATUS_PENDING, 0),
            "freshness": freshness,
        }

    # ------------------------------------------------------------------ 处理

    def resolve(
        self,
        recon_id: uuid.UUID,
        status: str,
        user_id: Optional[int],
        username: str,
        note: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> AssetReconciliation:
        """处理一条差异。状态机 + 并发安全 + 审计。

        并发安全靠带条件的 UPDATE（WHERE status='pending'）实现：
        两个请求同时到，只有一个 rowcount=1，另一个必然失败。
        不需要额外加锁，这也是 PRD 明确要求的"不引入额外锁"。
        """
        if status not in TERMINAL_STATUSES:
            raise ValueError(
                f"非法目标状态 {status}，只能是 {'/'.join(TERMINAL_STATUSES)}"
            )

        row = self.db.get(AssetReconciliation, recon_id)
        if row is None:
            raise LookupError("对账记录不存在")
        if row.status != STATUS_PENDING:
            raise ValueError(
                f"该差异已被处理为 {row.status}（处理人 {row.resolved_by or '未知'}），不可重复处理"
            )

        now = _utcnow()
        result = self.db.execute(
            update(AssetReconciliation)
            .where(
                AssetReconciliation.id == recon_id,
                AssetReconciliation.status == STATUS_PENDING,  # 关键：并发护栏
            )
            .values(
                status=status,
                resolved_by=username,
                resolved_at=now,
                resolve_note=note,
            )
        )
        if result.rowcount != 1:
            self.db.rollback()
            raise ValueError("该差异刚被其他人处理，请刷新后重试")

        self.db.add(
            AuditLog(
                user_id=user_id,
                username=username,
                action="resolve",
                resource_type="asset_reconciliation",
                # resource_id 是 BigInteger，存不了 UUID；沿用本项目既有惯例：
                # 置 None，把 UUID 放进 resource_name。
                resource_id=None,
                resource_name=f"reconciliation:{recon_id}",
                old_values={"status": STATUS_PENDING},
                new_values={
                    "status": status,
                    "reconciliation_type": row.reconciliation_type,
                    "asset_id": str(row.asset_id) if row.asset_id else None,
                    "run_id": str(row.run_id),
                    "note": note,
                },
                ip_address=ip_address,
                status="success",
            )
        )
        self.db.commit()
        self.db.refresh(row)
        return row
