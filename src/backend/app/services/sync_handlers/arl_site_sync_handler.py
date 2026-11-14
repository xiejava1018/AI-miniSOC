"""ARL 站点/端口观测同步处理器（OH-ARL.2 + OH-ARL.3，S2/多源融合接入）。

数据流（docs/design/2026-11-14-ARL-Next集成设计方案.md §4.1/§5.7）：
  arl-collector（asset_site + asset_ip 规范化，5 端点拉模型）
    → POST /data/sync (data_type=arl_site)
    → 本 handler
      ├─ IP 命中台账 → upsert soc_asset_sources('arl-next') + soc_asset_ports
      │                 多源融合（sources JSONB 追加 / last_seen_by_source 各记）
      └─ IP 未命中   → soc_scan_findings 旁路（discovery_source='arl-next'）
                        → F1.3 判 shadow → 确认工作台（零直写 soc_assets，
                          不切断 shadow 链路——discovery_sync_handler.py 头部警告）

设计要点（design §5.7/§5.8）：
  - **不调用 record_observation**：ARL 是外部探测（外部可达 ≠ 管理通道在线），
    观测时间记在 soc_asset_sources.last_seen_at / 端口 last_seen_by_source
    供参考展示，不参与失联（offline）判定。
  - 幂等：发现批次按 **UTC 日期** 生成 uuid5（同一天重推 upsert 刷新，
    不按轮次产生新行——30min 一轮否则 findings 表膨胀）。
  - 批次行：soc_scanner_tasks 建 mode='arl_sync' 日期批次行（任务中心可见；
    该表无 CHECK 约束，baseline 迁移 s1a2b3c4d5e6 已核）。
  - source_health 独立 key 'arl:sync'（与采集器整体健康分开），
    同步失败推送由场景 1 按 key 通用检查自动覆盖（零开发）。
"""

import ipaddress
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_port import AssetPort
from app.models.asset_source import AssetSource
from app.models.scanner_models import ScanFinding, ScannerTask
from app.services.sync_handlers.base import BaseSyncHandler

logger = logging.getLogger(__name__)

# P4 WO-2 同款：source → source_health source_key 映射
_SOURCE_HEALTH_KEYS = {
    "arl-next": "arl:sync",
    "arl": "arl:sync",
}
_SOURCE_HEALTH_INTERVALS = {
    "arl-next": 1800,
    "arl": 1800,
}

# 批次 UUID 命名空间（uuid5 确定性：同一天同一批次 → 发现表按天聚合）
_BATCH_NS = uuid.uuid5(uuid.NAMESPACE_URL, "arl-next-sync")


def _day_utc() -> datetime:
    return datetime.now(timezone.utc)


def _batch_uuid(prefix: str, day: datetime) -> uuid.UUID:
    return uuid.uuid5(_BATCH_NS, f"{prefix}-{day:%Y-%m-%d}")


def _ensure_scanner_task_batch(db: Session, batch: uuid.UUID, day: datetime) -> None:
    """soc_scanner_tasks 日期批次行（mode='arl_sync'）。

    scan_findings.scan_task_uuid 软关联到此表 task_uuid；日期复用——
    首轮创建，后续轮只刷新时间。任务中心可见（design OH-ARL.4）。
    """
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


def _is_public(ip: str) -> bool:
    try:
        return not ipaddress.ip_address(ip).is_private
    except ValueError:
        return False


def _upsert_arl_source(db: Session, asset_id, item: dict, now: datetime) -> None:
    """upsert source='arl-next' 的 soc_asset_sources 记录（§5.3 映射）。"""
    row = (
        db.query(AssetSource)
        .filter(AssetSource.asset_id == asset_id, AssetSource.source == "arl-next")
        .one_or_none()
    )
    metadata = {
        k: v for k, v in {
            "url": item.get("url"),
            "title": item.get("title"),
            "fingers": item.get("fingers"),
            "ip_type": item.get("ip_type"),
            "via_domain": item.get("via_domain"),
            "task_id": item.get("task_id"),
        }.items() if v not in (None, "", [])
    }
    if row is None:
        db.add(AssetSource(
            asset_id=asset_id,
            source="arl-next",
            source_id=item.get("scope_id") or item.get("task_id") or None,
            source_status="observed",
            last_seen_at=now,
            source_metadata=metadata or None,
        ))
    else:
        row.last_seen_at = now
        row.source_status = "observed"
        if item.get("scope_id"):
            row.source_id = item["scope_id"]
        if metadata:
            # 合并而非覆盖（保历史 fingers 摘要的键）
            merged = dict(row.source_metadata or {})
            merged.update(metadata)
            row.source_metadata = merged


def _upsert_port_observation(db: Session, item: dict, now: datetime) -> None:
    """端口多源融合（§5.5）：(asset_ip, port, protocol) upsert，
    sources JSONB 追加 'arl-next'、last_seen_by_source 记观测时间。
    不覆盖既有 service/version（补充语义，§5.8 谁权威表）。"""
    protocol = "tcp"  # 站点 scheme http/https 均为 tcp 承载
    row = (
        db.query(AssetPort)
        .filter(
            AssetPort.asset_ip == item["ip"],
            AssetPort.port == int(item["port"]),
            AssetPort.protocol == protocol,
        )
        .one_or_none()
    )
    sources = list(row.sources or []) if row is not None else []
    if "arl-next" not in sources:
        sources.append("arl-next")
    last_seen_map = dict(row.last_seen_by_source or {}) if row is not None else {}
    last_seen_map["arl-next"] = now.isoformat()
    if row is None:
        db.add(AssetPort(
            asset_ip=item["ip"],
            port=int(item["port"]),
            protocol=protocol,
            state="open",
            service=item.get("service") or item.get("scheme"),
            version=item.get("product"),
            sources=sources,
            last_seen_by_source=last_seen_map,
            last_seen=now,
        ))
    else:
        row.sources = sources
        row.last_seen_by_source = last_seen_map
        row.last_seen = now
        # 补充语义：现值为空才写（scanner/nmap 的识别更权威时不覆盖）
        if not row.service and (item.get("service") or item.get("scheme")):
            row.service = item.get("service") or item.get("scheme")
        if not row.version and item.get("product"):
            row.version = item.get("product")


class ArlSiteSyncHandler(BaseSyncHandler):
    """ARL 站点/端口观测同步（data_type=arl_site）。"""

    data_type = "arl_site"

    # 实例级缓冲（照 DiscoverySyncHandler._last_affected_findings 先例；
    # SYNC_HANDLERS 为模块级单例 + single_worker_guard 单 worker 前提）
    _batch: uuid.UUID | None = None

    def handle(self, source: str, items: list[dict], db: Session,
               task_uuid: str | None = None) -> dict:
        """源级 try/except + sync_task + source_health 双上报
        （照 DiscoverySyncHandler.handle / NatSyncHandler.handle 模式）。"""
        from app.models.sync_task import SyncTask

        day = _day_utc()
        self._batch = _batch_uuid("arl-site", day)
        try:
            sync_task = SyncTask(
                sync_type="collector",
                status="running",
                total_count=len(items),
                started_at=day,
            )
            db.add(sync_task)
            db.flush()

            _ensure_scanner_task_batch(db, self._batch, day)

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
            logger.error("ArlSiteSyncHandler.handle 源级失败 source=%s err=%s", source, e)
            try:
                from app.core import database as _db
                from app.services.source_health import SourceHealthRecorder
                fail_db = _db.SessionLocal()
                try:
                    SourceHealthRecorder(fail_db).record_failure(
                        key := _SOURCE_HEALTH_KEYS.get(source, f"{source}:{self.data_type}"),
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
        port = item.get("port")
        if port is None:
            raise ValueError("缺少 port 字段")
        try:
            int(port)
        except (TypeError, ValueError):
            raise ValueError(f"port 非法: {port!r}")

    def _item_key(self, item: dict) -> str:
        return f"{item.get('ip', '?')}:{item.get('port', '?')}"

    def _handle_one(self, source: str, item: dict, db: Session) -> dict[str, int]:
        """§4.1/§5.7：IP 命中 → 来源溯源 + 端口融合；未命中 → 发现旁路。"""
        now = _day_utc()
        item = dict(item)
        item["ip"] = item["ip"].strip()
        if item.get("port") is not None:
            item["port"] = int(item["port"])

        asset = (
            db.query(Asset)
            .filter(Asset.asset_ip == item["ip"])
            .one_or_none()
        )
        if asset is not None:
            _upsert_arl_source(db, asset.id, item, now)
            _upsert_port_observation(db, item, now)
            # 注意：不调用 record_observation（§5.8 失联判定以管理通道为准）
            return {"updated": 1}

        # 未命中 → soc_scan_findings 旁路（discovery_source='arl-next'）
        existing = (
            db.query(ScanFinding)
            .filter(
                ScanFinding.scan_task_uuid == self._batch,
                ScanFinding.asset_ip == item["ip"],
            )
            .one_or_none()
        )
        raw = {
            k: v for k, v in {
                "url": item.get("url"),
                "title": item.get("title"),
                "fingers": item.get("fingers"),
                "product": item.get("product"),
                "service": item.get("service"),
                "http_status": item.get("http_status"),
                "via_domain": item.get("via_domain"),
                "task_id": item.get("task_id"),
            }.items() if v not in (None, "", [])
        }
        exposure = "public" if _is_public(item["ip"]) else "internal"
        if existing is not None:
            existing.last_seen = now
            existing.raw_data = raw or existing.raw_data
            existing.exposure = exposure
            return {"updated": 1}
        db.add(ScanFinding(
            scan_task_uuid=self._batch,
            asset_ip=item["ip"],
            exposure=exposure,
            discovery_source="arl-next",
            finding_status="new",
            first_seen=now,
            last_seen=now,
            raw_data=raw or None,
        ))
        # 同批次内多条同 IP item 依赖此 flush 可见（sessionmaker autoflush=False，
        # 否则第二条 _handle_one 查不到 pending 行 → 撞 uq_scan_findings_task_ip）
        db.flush()
        return {"created": 1}
