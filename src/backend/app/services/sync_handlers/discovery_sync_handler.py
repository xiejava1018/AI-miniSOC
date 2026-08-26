"""
发现同步处理器（P3/F-S1 内网资产发现 → soc_scan_findings）

设计依据：docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md §6.2.1

核心修复（ADR-6）：scanner 不直接写 soc_assets，而是落独立的 soc_scan_findings；
台账写入仅在用户「一键纳管」时由 /api/v1/scan/findings/{id}/adopt 完成。

为什么：直接写台账会切断 F1.3 shadow 链路（F1.3 shadow 循环只遍历 Wazuh agents，
已入库资产永不被判 shadow）；同时 nmap -sn 瞬时/重复命中会污染主资产列表与风险评分。

唯一索引：(scan_task_uuid, asset_ip) → upsert（已存在则刷新 last_seen + 字段）。
"""

import logging
from datetime import datetime, timezone
from typing import Dict

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.scanner_models import ScanFinding
from app.services.sync_handlers.base import BaseSyncHandler

logger = logging.getLogger(__name__)


class DiscoverySyncHandler(BaseSyncHandler):
    """发现数据同步（数据来源：scanner 内网/外网发现扫描）。

    handle() 镜像 AssetSyncHandler.handle() 的同款 source_health 上报逻辑，
    让 /data-health 自动反映 scanner:discovery 通道状态。
    """

    data_type = "discovery"

    def handle(self, source: str, items: list[dict], db: Session) -> dict:
        """P4 WO-2 镜像：源级 try/except + sync_task + source_health 上报。

        与 AssetSyncHandler.handle() / PortSyncHandler.handle() 同模式——Phase 2
        三个 handler 同款包装，未来若重构可统一抽到 BaseSyncHandler（本次保持最小改动）。
        """
        from app.services.sync_handlers.asset_sync_handler import (
            _SOURCE_HEALTH_KEYS,
            _SOURCE_HEALTH_INTERVALS,
        )
        from app.models.sync_task import SyncTask

        try:
            sync_task = SyncTask(
                sync_type="collector",
                status="running",
                total_count=len(items),
                started_at=datetime.now(timezone.utc),
            )
            db.add(sync_task)
            db.flush()

            stats = super().handle(source, items, db)

            sync_task.status = "completed"
            sync_task.created_count = stats["created"]
            sync_task.updated_count = stats["updated"]
            sync_task.failed_count = stats["failed"]
            sync_task.completed_at = datetime.now(timezone.utc)
            if stats["failed"] > 0:
                sync_task.error_message = (
                    f"{stats['failed']} items failed; "
                    f"see dead_letter batch={stats['dead_letter_batch_id']}"
                )
            db.commit()

            # P4 WO-2：source_health 上报（失败>0 不记 failure）
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
            logger.error("DiscoverySyncHandler.handle 源级失败 source=%s err=%s", source, e)
            try:
                from app.services.source_health import SourceHealthRecorder
                key = _SOURCE_HEALTH_KEYS.get(source, f"{source}:{self.data_type}")
                from app.core import database as _db
                fail_db = _db.SessionLocal()
                try:
                    SourceHealthRecorder(fail_db).record_failure(
                        key, source_type=source, error=str(e)[:1000],
                    )
                    fail_db.commit()
                finally:
                    fail_db.close()
            except Exception:
                logger.debug("source_health record_failure failed", exc_info=True)
            raise

    def _validate_one(self, item: dict) -> None:
        """校验单条 discovery item。

        必填字段（final.md §6.2.1）：
          - scan_task_uuid  UUID（关联 soc_scanner_tasks.task_uuid）
          - asset_ip        str
        可选：mac_address / os_guess / exposure / scanner_id / raw_data
        """
        required = {"scan_task_uuid", "asset_ip"}
        missing = [k for k in required if k not in item or item.get(k) in (None, "")]
        if missing:
            raise ValueError(f"缺少字段或字段为空: {sorted(missing)}")

        exposure = item.get("exposure")
        if exposure and exposure not in ("internal", "public"):
            raise ValueError(f"非法 exposure: {exposure!r}（仅 internal/public）")

    def _item_key(self, item: dict) -> str:
        """用于死信 item_key 字段。"""
        return f"{item.get('scan_task_uuid', '?')}:{item.get('asset_ip', '?')}"

    def _handle_one(self, source: str, item: dict, db: Session) -> Dict[str, int]:
        """按 (scan_task_uuid, asset_ip) upsert ScanFinding。

        关键设计（ADR-6）：
          - 反查 soc_assets 写 matched_asset_id（仅提示，F1.3 据此跳过 shadow）
          - 已 adopted/ignored 的 finding 由 finding_status 控制，不再 upsert（保护处置状态）
          - 已存在的 finding 更新 last_seen + 字段；finding_status 不被覆盖
        """
        existing = db.query(ScanFinding).filter(
            ScanFinding.scan_task_uuid == item["scan_task_uuid"],
            ScanFinding.asset_ip == item["asset_ip"],
        ).one_or_none()

        # 反查台账 IP 命中情况（仅写 matched_asset_id 字段，不动台账）
        matched_asset = db.query(Asset).filter(
            Asset.asset_ip == item["asset_ip"],
        ).first()

        now = datetime.now(timezone.utc)
        if existing is not None:
            # 已存在 → 刷新字段（finding_status 不动——保护人工处置结果）
            existing.last_seen = now
            existing.mac_address = item.get("mac_address") or existing.mac_address
            existing.os_guess = item.get("os_guess") or existing.os_guess
            existing.scanner_id = item.get("scanner_id") or existing.scanner_id
            existing.exposure = item.get("exposure", existing.exposure or "internal")
            existing.raw_data = item.get("raw_data", existing.raw_data)
            # matched_asset_id 只在已有值或新反查命中时更新（避免覆盖人工维护的 adopted 关联）
            if matched_asset and not existing.matched_asset_id:
                existing.matched_asset_id = matched_asset.id
                # IP 已命中台账 → finding_status 提升为 known（F1.3 据此跳过）
                if existing.finding_status == "new":
                    existing.finding_status = "known"
            return {"updated": 1}

        # 新建
        finding = ScanFinding(
            scan_task_uuid=item["scan_task_uuid"],
            asset_ip=item["asset_ip"],
            mac_address=item.get("mac_address"),
            os_guess=item.get("os_guess"),
            exposure=item.get("exposure", "internal"),
            discovery_source="scanner",
            scanner_id=item.get("scanner_id"),
            matched_asset_id=matched_asset.id if matched_asset else None,
            finding_status="known" if matched_asset else "new",
            first_seen=now,
            last_seen=now,
            raw_data=item.get("raw_data"),
        )
        db.add(finding)
        return {"created": 1}