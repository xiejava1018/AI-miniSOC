"""ARL 漏洞/发现同步处理器（OH-ARL.2，§5.5/§5.6 冲突 1/2 分流）。

数据流（docs/design/2026-11-14-ARL-Next集成设计方案.md §4.1）：
  arl-collector（asset_vuln + asset_nuclei_result 规范化）
    → POST /data/sync (data_type=arl_vuln)
    → 本 handler，双落点分流（§5.6 冲突 1）：
      ├─ 命中资产 且 有 CVE 编号 → soc_vulnerabilities（type='arl_poc'）
      │   + soc_asset_vulnerabilities(scanner='arl-next') —— 置信度「已验证」，
      │     SLA 机制现成；scan_task_id FK → soc_scan_tasks 日期批次行
      │     （vulnerability.ScanTask，task_type='arl_sync'；冲突 2 处置）
      └─ 无 CVE 或未命中资产   → soc_scan_findings 旁路
          （discovery_source='arl-next'，raw_data.vulns 按 IP 聚合——
            唯一键 (scan_task_uuid, asset_ip) 不改迁移，同 IP 多插件
            聚合为数组，Swagger 泄露类高价值发现完整保留）

批次幂等（§5.7）：UTC 日期 uuid5——同天重推 upsert 刷新，不按轮次增行。
source_health key 'arl:sync'（同 arl_site handler）。
"""

import ipaddress
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_source import AssetSource
from app.models.scanner_models import ScanFinding, ScannerTask
from app.models.vulnerability import AssetVulnerability, ScanTask, Vulnerability
from app.services.sync_handlers.base import BaseSyncHandler

logger = logging.getLogger(__name__)

_SOURCE_HEALTH_KEYS = {
    "arl-next": "arl:sync",
    "arl": "arl:sync",
}
_SOURCE_HEALTH_INTERVALS = {
    "arl-next": 1800,
    "arl": 1800,
}

_BATCH_NS = uuid.uuid5(uuid.NAMESPACE_URL, "arl-next-sync")

# ARL 归档态无结构化 severity（实测）；nuclei 有则映射，缺失默认 medium（诚实：
# raw_data 记录 source_severity 缺失）
_SEVERITY_MAP = {
    "critical": "critical", "high": "high", "medium": "medium",
    "low": "low", "info": "low",
}
_DEFAULT_SEVERITY = "medium"


def _day_utc() -> datetime:
    return datetime.now(timezone.utc)


def _batch_uuid(prefix: str, day: datetime) -> uuid.UUID:
    return uuid.uuid5(_BATCH_NS, f"{prefix}-{day:%Y-%m-%d}")


def _is_public(ip: str) -> bool:
    try:
        return not ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def _ensure_vuln_scan_task(db: Session, day: datetime, ips: list[str],
                           summary: dict) -> ScanTask:
    """soc_scan_tasks（vulnerability.ScanTask）日期批次行——
    AssetVulnerability.scan_task_id 的 FK 目标（冲突 2 处置）。
    task_type 无 CHECK（模型已核），新增 'arl_sync' 软约定。"""
    name = f"ARL 漏洞同步批次 {day:%Y-%m-%d}"
    row = db.query(ScanTask).filter(ScanTask.name == name).one_or_none()
    if row is None:
        row = ScanTask(
            task_type="arl_sync",
            name=name,
            target_assets={"ips": sorted(set(ips))},
            status="completed",
            started_at=day,
            completed_at=day,
            result_summary=summary,
        )
        db.add(row)
        db.flush()
    else:
        row.result_summary = summary
        row.completed_at = day
    return row


def _ensure_finding_task_batch(db: Session, batch: uuid.UUID,
                               day: datetime) -> None:
    """soc_scanner_tasks 日期批次行（scan_findings 软关联目标；任务中心可见）。"""
    row = db.query(ScannerTask).filter(ScannerTask.task_uuid == batch).one_or_none()
    if row is None:
        db.add(ScannerTask(
            task_uuid=batch,
            mode="arl_sync",
            scope="scheduled",
            run_reason="scheduled",
            status="success",
            triggered_by="arl-collector",
            started_at=day,
            finished_at=day,
        ))
    else:
        row.finished_at = day


def _upsert_arl_source(db: Session, asset_id, item: dict, now: datetime) -> None:
    row = (
        db.query(AssetSource)
        .filter(AssetSource.asset_id == asset_id, AssetSource.source == "arl-next")
        .one_or_none()
    )
    metadata = {"vuln_seen_at": now.isoformat()}
    if row is None:
        db.add(AssetSource(
            asset_id=asset_id,
            source="arl-next",
            source_id=item.get("scope_id") or item.get("task_id") or None,
            source_status="observed",
            last_seen_at=now,
            source_metadata=metadata,
        ))
    else:
        row.last_seen_at = now
        merged = dict(row.source_metadata or {})
        merged.update(metadata)
        row.source_metadata = merged


class ArlVulnSyncHandler(BaseSyncHandler):
    """ARL 漏洞/发现同步（data_type=arl_vuln）。"""

    data_type = "arl_vuln"

    _batch: uuid.UUID | None = None
    _vuln_batch: ScanTask | None = None

    def handle(self, source: str, items: list[dict], db: Session,
               task_uuid: str | None = None) -> dict:
        from app.models.sync_task import SyncTask

        day = _day_utc()
        self._batch = _batch_uuid("arl-vuln", day)
        self._vuln_batch = None
        try:
            sync_task = SyncTask(
                sync_type="collector",
                status="running",
                total_count=len(items),
                started_at=day,
            )
            db.add(sync_task)
            db.flush()

            _ensure_finding_task_batch(db, self._batch, day)

            stats = super().handle(source, items, db)

            sync_task.status = "completed"
            sync_task.created_count = stats["created"]
            sync_task.updated_count = stats["updated"]
            sync_task.failed_count = stats["failed"]
            sync_task.completed_at = _day_utc()
            if stats["failed"] > 0:
                sync_task.error_message = (
                    f"{stats['failed']} items failed; "
                    f"see dead_letter batch={stats['dead_letter_batch_id']}"
                )
            db.commit()

            try:
                from app.services.source_health import SourceHealthRecorder
                key = _SOURCE_HEALTH_KEYS.get(source, f"{source}:{self.data_type}")
                SourceHealthRecorder(db).record_success(
                    key,
                    source_type=source,
                    records_count=stats.get("total"),
                    expected_interval_seconds=_SOURCE_HEALTH_INTERVALS.get(source),
                )
                db.commit()
            except Exception:
                db.rollback()
                logger.debug("source_health record_success failed", exc_info=True)
            return stats
        except Exception as e:
            logger.error("ArlVulnSyncHandler.handle 源级失败 source=%s err=%s", source, e)
            try:
                from app.core import database as _db
                from app.services.source_health import SourceHealthRecorder
                fail_db = _db.SessionLocal()
                try:
                    SourceHealthRecorder(fail_db).record_failure(
                        _SOURCE_HEALTH_KEYS.get(source, f"{source}:{self.data_type}"),
                        source_type=source,
                        error=f"{type(e).__name__}: {e}"[:1000],
                    )
                    fail_db.commit()
                finally:
                    fail_db.close()
            except Exception:
                logger.debug("source_health record_failure failed", exc_info=True)
            raise

    def _validate_one(self, item: dict) -> None:
        ip = (item.get("ip") or "").strip()
        if not ip:
            raise ValueError("缺少 ip 字段")
        try:
            ipaddress.ip_address(ip)
        except ValueError:
            raise ValueError(f"ip 不是合法 IP: {ip!r}")
        if not (item.get("plugin_name") or item.get("url")):
            raise ValueError("plugin_name / url 至少其一")

    def _item_key(self, item: dict) -> str:
        return f"{item.get('ip', '?')}:{item.get('plugin_name', '?')}"

    def _handle_one(self, source: str, item: dict, db: Session) -> dict[str, int]:
        now = _day_utc()
        item = dict(item)
        item["ip"] = item["ip"].strip()

        asset = (
            db.query(Asset)
            .filter(Asset.asset_ip == item["ip"])
            .one_or_none()
        )
        cve_ids = item.get("cve_ids") or []

        # 分流 1（§5.6 冲突 1）：命中资产 + 有 CVE → 漏洞模型
        if asset is not None and cve_ids:
            _upsert_arl_source(db, asset.id, item, now)
            day = now
            if self._vuln_batch is None:
                self._vuln_batch = _ensure_vuln_scan_task(
                    db, day, [item["ip"]],
                    {"note": "按需扩展；最终汇总在 handle 尾部更新"},
                )
            created = 0
            for cve in cve_ids:
                vuln = (
                    db.query(Vulnerability)
                    .filter(Vulnerability.cve_id == cve)
                    .one_or_none()
                )
                if vuln is None:
                    severity = _SEVERITY_MAP.get(
                        str(item.get("severity") or "").lower(),
                        _DEFAULT_SEVERITY,
                    )
                    vuln = Vulnerability(
                        cve_id=cve,
                        title=item.get("app_name") or item.get("plugin_name") or cve,
                        severity=severity,
                        type="arl_poc",  # 新枚举值（模型无 CHECK）；区分于 sca/scap
                    )
                    db.add(vuln)
                    db.flush()
                    created += 1
                link = (
                    db.query(AssetVulnerability)
                    .filter(
                        AssetVulnerability.asset_id == asset.id,
                        AssetVulnerability.vulnerability_id == vuln.id,
                        AssetVulnerability.scanner == "arl-next",
                    )
                    .one_or_none()
                )
                if link is None:
                    link = AssetVulnerability(
                        asset_id=asset.id,
                        vulnerability_id=vuln.id,
                        scanner="arl-next",
                        status="open",
                        detected_at=now,
                        scan_task_id=self._vuln_batch.id,
                    )
                    db.add(link)
                else:
                    link.detected_at = now
                    link.scan_task_id = self._vuln_batch.id
            if created:
                return {"created": created}
            return {"updated": len(cve_ids)}

        # 分流 2：无 CVE 或未命中资产 → soc_scan_findings 旁路
        #   同 IP 多插件聚合进 raw_data.vulns（唯一键 (scan_task_uuid, asset_ip)）
        existing = (
            db.query(ScanFinding)
            .filter(
                ScanFinding.scan_task_uuid == self._batch,
                ScanFinding.asset_ip == item["ip"],
            )
            .one_or_none()
        )
        vuln_entry = {
            k: v for k, v in {
                "plugin_name": item.get("plugin_name"),
                "app_name": item.get("app_name"),
                "url": item.get("url"),
                "cve_ids": cve_ids,
                "source_table": item.get("source_table"),
                "task_id": item.get("task_id"),
            }.items() if v not in (None, "", [])
        }
        exposure = "public" if _is_public(item["ip"]) else "internal"
        if existing is not None:
            existing.last_seen = now
            existing.exposure = exposure
            raw = dict(existing.raw_data or {})
            vulns = list(raw.get("vulns") or [])
            key = (vuln_entry.get("plugin_name"), vuln_entry.get("url"))
            if not any(
                (v.get("plugin_name"), v.get("url")) == key for v in vulns
            ):
                vulns.append(vuln_entry)
            raw["vulns"] = vulns
            existing.raw_data = raw
            return {"updated": 1}

        db.add(ScanFinding(
            scan_task_uuid=self._batch,
            asset_ip=item["ip"],
            exposure=exposure,
            discovery_source="arl-next",
            finding_status="new",
            first_seen=now,
            last_seen=now,
            raw_data={"vulns": [vuln_entry]} if vuln_entry else None,
        ))
        # 同批次内多条同 IP item 依赖此 flush 可见（autoflush=False，见 arl_site 同注）
        db.flush()
        return {"created": 1}
