"""
端口同步处理器（P3/F-S2 公网暴露面扫描采集器 → 资产端口表）

设计依据：docs/design/2026-08-26-asset-discovery-and-attack-surface-scanner-final.md §6.2.2
通过 /api/v1/data/sync 接收 scanner 推送的端口数据（data_type="port"）。
复用 AssetPort 模型（已存在）；按 (asset_ip, port, protocol) 唯一约束做 upsert。
反查 soc_assets.id 关联 asset_id；找不到 IP 不报错（公网 IP 也允许 asset_id=NULL）。

不重复造轮子：
- 死信 + 逐条 try/except + sync_task 状态机 + source_health record_success
  全部由 handle() 包装（镜像 AssetSyncHandler.handle() 模式，P4 已验证）。
- 子类只需：_validate_one() 字段校验 + _handle_one() 单条 upsert。
"""

import logging
from datetime import datetime, timezone
from typing import Dict

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_port import AssetPort
from app.models.sync_task import SyncTask
from app.services.sync_handlers.base import BaseSyncHandler

logger = logging.getLogger(__name__)


class PortSyncHandler(BaseSyncHandler):
    """端口数据同步（数据来源：scanner 公网暴露面扫描）。

    handle() 镜像 AssetSyncHandler.handle()：P4 WO-2 补丁要求所有 handler 统一上
    报 source_health（成功/失败），/data-health 才能反映真实通道状态。
    """

    data_type = "port"

    def handle(self, source: str, items: list[dict], db: Session) -> dict:
        """P4 WO-2 镜像：源级 try/except + sync_task + source_health 上报。

        与 AssetSyncHandler.handle() 同模式，未来若新增 handler 应统一抽到
        BaseSyncHandler；本次为最小改动（CLAUDE.md 教训：遵循已有范式）。
        """
        from app.services.sync_handlers.asset_sync_handler import (
            _SOURCE_HEALTH_KEYS,
            _SOURCE_HEALTH_INTERVALS,
        )
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

            # P4 WO-2：source_health 上报（失败>0 不记 failure，理由同 asset handler）
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
            logger.error("PortSyncHandler.handle 源级失败 source=%s err=%s", source, e)
            try:
                from app.services.source_health import SourceHealthRecorder
                key = _SOURCE_HEALTH_KEYS.get(source, f"{source}:{self.data_type}")
                from app.core import database as _db
                fail_db = _db.SessionLocal()
                try:
                    SourceHealthRecorder(fail_db).record_failure(
                        key,
                        source_type=source,
                        error=str(e)[:1000],
                    )
                    fail_db.commit()
                finally:
                    fail_db.close()
            except Exception:
                logger.debug("source_health record_failure failed", exc_info=True)
            raise

    def _validate_one(self, item: dict) -> None:
        """校验单条 port item。raise ValueError → 父类自动入死信。

        必填字段（final.md §6.2.2）：
          - asset_ip   str (IPv4/IPv6)
          - port       int 1-65535
          - protocol   'tcp'|'udp'
        可选字段：service / version / service_banner / state / scan_time
        """
        required = {"asset_ip", "port", "protocol"}
        # 检查键存在 + 值非空（in keys 检查键名，not value 检查空值/None）
        missing = [k for k in required if k not in item or item.get(k) in (None, "")]
        if missing:
            raise ValueError(f"缺少字段或字段为空: {sorted(missing)}")
        if not isinstance(item["port"], int) or not (1 <= item["port"] <= 65535):
            raise ValueError(f"非法端口号: {item['port']!r}")
        proto = str(item["protocol"]).lower()
        if proto not in ("tcp", "udp"):
            raise ValueError(f"非法协议: {item['protocol']!r}（仅 tcp/udp）")
        # 把 protocol 标准化成小写（避免 TCP/Tcp 等变体）
        item["protocol"] = proto

    def _item_key(self, item: dict) -> str:
        """用于死信 item_key 字段（便于按 IP 排查）。"""
        return f"{item.get('asset_ip', '?')}:{item.get('port', '?')}/{item.get('protocol', '?')}"

    def _handle_one(self, source: str, item: dict, db: Session) -> Dict[str, int]:
        """按 (asset_ip, port, protocol) upsert AssetPort。

        返回 {"created":1} 或 {"updated":1}。

        重要约束（避免污染既有数据）：
          - asset_id 只在 IP 命中 soc_assets 时挂上；公网 IP 允许 asset_id=NULL
          - vulnerability 列本期由 F-S2 留空，Phase 4 NSE 填充
          - last_seen 每次都刷新（不论 created/updated）
          - 不动 asset_id（资产换 IP 时由人工编辑，避免越权修改）
        """
        existing = db.query(AssetPort).filter(
            AssetPort.asset_ip == item["asset_ip"],
            AssetPort.port == item["port"],
            AssetPort.protocol == item["protocol"],
        ).one_or_none()

        if existing is not None:
            # 更新：服务指纹 + 最后扫描时间（field-by-field，避免空值覆盖真值）
            existing.service = item.get("service") or existing.service
            existing.version = item.get("version") or existing.version
            existing.service_banner = item.get("service_banner") or existing.service_banner
            existing.last_seen = item.get("scan_time") or datetime.now(timezone.utc)
            existing.state = item.get("state", existing.state or "open")
            # P4-B-α：合并新扫到的 CVE 列表（去重 + 保留历史 CVE）
            new_cves = item.get("cves") or []
            if new_cves:
                existing_vulns = list(existing.vulnerabilities or [])
                merged = sorted(set(existing_vulns) | set(new_cves))
                existing.vulnerabilities = merged
            return {"updated": 1}

        # 新建：反查 asset_id（IP 命中则挂上，纯公网 IP 允许 NULL）
        asset = db.query(Asset).filter(Asset.asset_ip == item["asset_ip"]).first()
        port = AssetPort(
            asset_id=asset.id if asset else None,
            asset_ip=item["asset_ip"],
            port=item["port"],
            protocol=item["protocol"],
            state=item.get("state", "open"),
            service=item.get("service"),
            version=item.get("version"),
            service_banner=item.get("service_banner"),
            vulnerabilities=list(item.get("cves") or []),
            # scan_time 字段为非空；缺则用 now()
            last_seen=item.get("scan_time") or datetime.now(timezone.utc),
        )
        db.add(port)
        return {"created": 1}