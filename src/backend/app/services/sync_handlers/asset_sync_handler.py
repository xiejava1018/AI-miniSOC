"""
资产同步处理器

处理 Collector 推送的资产数据：
- 按 (network_segment, asset_ip) 查重（匹配唯一约束）
- 增量对比：只更新变化的字段
- 变更记录：写入 AssetChangeLog
- 任务跟踪：创建 SyncTask 记录
- 数据来源：写入 soc_asset_sources（多来源支持）
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.asset_source import AssetSource
from app.models.sync_task import SyncTask
from app.models.asset_change_log import AssetChangeLog
from app.services.sync_handlers.base import BaseSyncHandler

logger = logging.getLogger(__name__)

# Asset 模型上允许 Collector 写入的字段白名单
# T4（决策1，2026-08-15）：移除 criticality —— 关键度是业务属性，
# 只能由安全运营人工维护（资产页/手动提升），采集器无权覆盖；
# 否则 TP-Link 每 5 分钟推送会把回填后的 medium 覆盖回旧值。
_UPDATABLE_FIELDS = {
    "name", "asset_type", "asset_status", "mac_address",
    "network_zone", "asset_description",
    "data_source", "os_name", "os_version", "wazuh_agent_id",
}


class AssetSyncHandler(BaseSyncHandler):
    """资产同步处理器"""

    def handle(self, source: str, items: list[dict], db: Session) -> dict:
        print(f"[DEBUG] AssetSyncHandler.handle called: source={source}, items={len(items)}")
        logger.info(f"AssetSyncHandler.handle called: source={source}, items={len(items)}")
        stats = {
            "total": len(items),
            "created": 0,
            "updated": 0,
            "skipped": 0,
            "failed": 0,
            "errors": [],
        }

        sync_task = SyncTask(
            sync_type="collector",
            status="running",
            total_count=len(items),
            started_at=datetime.now(timezone.utc),
        )
        db.add(sync_task)
        db.flush()

        for item in items:
            try:
                result = self._upsert_asset(source, item, sync_task.id, db)
                stats[result] += 1
            except Exception as e:
                stats["failed"] += 1
                ip = item.get("asset_ip", "?")
                stats["errors"].append(f"{ip}: {str(e)}")
                logger.warning(f"同步资产失败 {ip}: {e}")

        db.flush()

        sync_task.status = "completed"
        sync_task.created_count = stats["created"]
        sync_task.updated_count = stats["updated"]
        sync_task.failed_count = stats["failed"]
        sync_task.completed_at = datetime.now(timezone.utc)
        if stats["errors"]:
            sync_task.error_message = "\n".join(stats["errors"])

        db.commit()
        logger.info(
            f"资产同步完成: source={source}, "
            f"total={stats['total']}, created={stats['created']}, "
            f"updated={stats['updated']}, skipped={stats['skipped']}, "
            f"failed={stats['failed']}"
        )
        return stats

    def _upsert_asset(self, source: str, item: dict, sync_task_id, db: Session) -> str:
        asset_ip = item.get("asset_ip")
        if not asset_ip:
            raise ValueError("缺少 asset_ip 字段")

        network_segment = item.get("network_segment", "default")

        existing: Optional[Asset] = db.query(Asset).filter(
            Asset.asset_ip == asset_ip,
            Asset.network_segment == network_segment,
        ).first()

        now = datetime.now(timezone.utc)

        if existing:
            return self._update_existing(existing, source, item, sync_task_id, now, db)
        else:
            return self._create_new(source, item, sync_task_id, now, db)

    def _create_new(self, source: str, item: dict, sync_task_id, now: datetime, db: Session) -> str:
        if "network_segment" not in item:
            item["network_segment"] = "default"

        valid_zones = {"intranet", "dmz", "office", "management", "other"}
        if item.get("network_zone") not in valid_zones:
            item["network_zone"] = "intranet"

        item["last_synced_at"] = now

        # 过滤掉不属于 Asset 模型的字段（如 source_id，它属于 AssetSource）
        asset_fields = {k: v for k, v in item.items() if k != "source_id"}
        # T4（决策1）：criticality 不变采集器控制 —— 新建时也忽略 payload 值，
        # 用模型默认 medium（保持与人工维护口径一致）
        asset_fields.pop("criticality", None)

        asset = Asset(**asset_fields)
        db.add(asset)
        db.flush()

        # 写入来源记录
        self._upsert_source_record(asset.id, source, item, now, db)

        self._log_change(asset_id=asset.id, sync_task_id=sync_task_id, change_type="created", db=db)
        logger.debug(f"创建资产: {item.get('asset_ip')}")
        return "created"

    def _update_existing(self, asset: Asset, source: str, item: dict, sync_task_id, now: datetime, db: Session) -> str:
        print(f"[DEBUG] _update_existing called for {asset.asset_ip}")
        changed_fields = []

        print(f"[DEBUG] _UPDATABLE_FIELDS: {_UPDATABLE_FIELDS}")
        print(f"[DEBUG] item keys: {list(item.keys())}")
        print(f"[DEBUG] asset.data_source: {getattr(asset, 'data_source', None)}")

        logger.info(f"Updating asset {asset.asset_ip}, item keys: {list(item.keys())}")
        logger.info(f"Current asset data_source: {getattr(asset, 'data_source', None)}, os_name: {getattr(asset, 'os_name', None)}")

        for field in _UPDATABLE_FIELDS:
            new_value = item.get(field)
            if new_value is None:
                continue
            old_value = getattr(asset, field, None)
            old_str = str(old_value) if old_value is not None else None
            new_str = str(new_value) if not isinstance(new_value, str) else new_value
            if old_str != new_str:
                logger.info(f"Field {field}: {old_str} -> {new_str}")
                print(f"[DEBUG] Updating field {field}: {old_str} -> {new_str}")
                setattr(asset, field, new_value)
                changed_fields.append((field, old_str, new_str))

        asset.last_synced_at = now

        # 更新来源记录（无论字段是否变化）
        self._upsert_source_record(asset.id, source, item, now, db)

        if not changed_fields:
            db.flush()  # 持久化 last_synced_at 和 source 记录
            logger.debug(f"跳过（无变化）: {asset.asset_ip}")
            return "skipped"

        for field_name, old_val, new_val in changed_fields:
            self._log_change(
                asset_id=asset.id, sync_task_id=sync_task_id,
                change_type="updated", field_name=field_name,
                old_value=str(old_val) if old_val is not None else None,
                new_value=str(new_val) if new_val is not None else None,
                db=db,
            )

        status_field = next((f for f in changed_fields if f[0] == "asset_status"), None)
        if status_field:
            self._log_change(
                asset_id=asset.id, sync_task_id=sync_task_id,
                change_type="status_changed", field_name="asset_status",
                old_value=status_field[1], new_value=status_field[2], db=db,
            )

        db.flush()
        logger.debug(f"更新资产: {asset.asset_ip}, 变更字段: {[f[0] for f in changed_fields]}")
        return "updated"

    def _upsert_source_record(self, asset_id, source: str, item: dict, now: datetime, db: Session):
        """
        写入/更新 soc_asset_sources 记录

        每个 (asset_id, source) 组合唯一，记录该来源看到的状态和特有数据。
        """
        existing_source = db.query(AssetSource).filter(
            AssetSource.asset_id == asset_id,
            AssetSource.source == source,
        ).first()

        # 构建来源特有的 metadata（只存该来源才有的数据）
        metadata = {}
        for key in ("ssid", "freq_name", "rssi", "ap_name", "conn_type",
                     "up_speed", "down_speed", "connect_date", "connect_time"):
            if item.get(key):
                metadata[key] = item[key]
        if item.get("mac_address"):
            metadata["mac_address"] = item["mac_address"]

        source_status = item.get("asset_status")
        source_id = item.get("source_id")

        if existing_source:
            existing_source.source_status = source_status
            existing_source.last_seen_at = now
            if metadata:
                existing_source.source_metadata = metadata
            if source_id:
                existing_source.source_id = source_id
        else:
            db.add(AssetSource(
                asset_id=asset_id,
                source=source,
                source_id=source_id,
                source_status=source_status,
                last_seen_at=now,
                source_metadata=metadata if metadata else None,
            ))

    @staticmethod
    def _log_change(asset_id, sync_task_id, change_type: str, db: Session,
                    field_name: Optional[str] = None,
                    old_value: Optional[str] = None,
                    new_value: Optional[str] = None):
        db.add(AssetChangeLog(
            asset_id=asset_id, sync_task_id=sync_task_id,
            change_type=change_type, field_name=field_name,
            old_value=old_value, new_value=new_value,
        ))
