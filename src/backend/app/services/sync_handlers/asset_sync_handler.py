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

# P4 WO-2：source → source_health source_key 映射。
# 采集器推送（tplink）与 wazuh agent 同步都流经本 handler，在 handle() 收尾
# 集中上报，即可覆盖全部资产类同步源（未来新采集器自动纳入）。
#
# P3/F-S2：加入 scanner 的两个通道键。
# 旧设计由每个 handler 独立维护 _SOURCE_HEALTH_KEYS；P3 阶段集中到此处以减少重复。
# PortSyncHandler.handle() 会镜像 AssetSyncHandler.handle() 的同款 source_health 上报逻辑。
_SOURCE_HEALTH_KEYS = {
    "tplink": "tplink:collector",
    "tplink-router": "tplink:collector",  # 采集器实际推送的 source 值（生产实测）
    "wazuh": "wazuh:agents",
    # P3 资产发现扫描器（docs/design/...-final.md §6.2.3）
    "scanner": "scanner:discovery",       # data_type="discovery" 通道
    "scanner-port": "scanner:ports",      # data_type="port" 通道
}

# P4 WO-2 补丁：预期间隔（秒），不传会让 _source_status() 跳过 degraded 判定（验收报告 #2）
# 300s = 5min，与现有采集器实测推送频率一致
_SOURCE_HEALTH_INTERVALS = {
    "tplink": 300,
    "tplink-router": 300,
    "wazuh": 300,
    "scanner": 300,       # P3：scanner 发现通道（与现有采集器同频）
    "scanner-port": 300,  # P3：scanner 端口通道
}

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
    """资产同步处理器（P2-T4：失败走死信）"""

    data_type = "asset"

    def handle(self, source: str, items: list[dict], db: Session, task_uuid: str | None = None) -> dict:
        """资产同步。task_uuid 参数本 handler 不使用，仅为与 port/discovery 一致接口。

        P4 WO-2 补丁：handle() 整体包 try/except，源级失败时记 record_failure
        （之前只有 record_success，且只在成功路径——handle() 抛错时
         任何 source_health 都不写，/data-health 页面假绿）
        """
        try:
            # P2-T4：创建批次 sync_task（保留 sync_tasks 跟踪能力），
            # 然后逐条调 _handle_one（base 已 try/except，失败入死信）。
            sync_task = SyncTask(
                sync_type="collector",
                status="running",
                total_count=len(items),
                started_at=datetime.now(timezone.utc),
            )
            db.add(sync_task)
            db.flush()

            # 调 base.handle（逐条 try/except + 死信）
            stats = super().handle(source, items, db)
            # 同步任务状态更新
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

            # P4 WO-2：数据源健康上报（成功/部分失败都算“采集活着”；
            # failed>0 不记 failure——逐条失败已入死信，整体中断才是源级故障）
            # v1.2 补丁：传 expected_interval_seconds 让 _source_status() 能判 degraded
            try:
                from app.services.source_health import SourceHealthRecorder
                key = _SOURCE_HEALTH_KEYS.get(source, f"{source}:assets")
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
            # P4 WO-2 补丁：源级失败（接 Wazuh API / DB 炸 / 未知异常）记 record_failure
            # 不吞异常——base.handle() 已有逐条 try/except，能逃到这里的都是真源级故障
            # 必须 raise，让上游 API 返 500（v1.0-v1.1 验收中也明确要求）
            logger.error("AssetSyncHandler.handle 源级失败 source=%s err=%s", source, e)
            try:
                from app.services.source_health import SourceHealthRecorder
                key = _SOURCE_HEALTH_KEYS.get(source, f"{source}:assets")
                # 用独立 session 防被外层 rollback 灭掉
                from app.core import database as _db
                fail_db = _db.SessionLocal()
                try:
                    SourceHealthRecorder(fail_db).record_failure(
                        key,
                        source_type=source,
                        error=f"{type(e).__name__}: {e}"[:1000],
                    )
                    fail_db.commit()
                finally:
                    fail_db.close()
            except Exception:
                logger.debug("source_health record_failure failed", exc_info=True)
            raise

    def _item_key(self, item: dict) -> str:
        """用于死信 item_key 字段（便于按 IP 排查）。"""
        return item.get("asset_ip", "?")

    def _validate_one(self, item: dict) -> None:
        """资产必须含 asset_ip 字段。"""
        if not item.get("asset_ip"):
            raise ValueError("缺少 asset_ip 字段")

    def _handle_one(self, source: str, item: dict, db: Session) -> dict:
        """单条 upsert，返回 {"created"|"updated"|"skipped"}。"""
        # 取出当前批次 sync_task_id（在 handle 中创建的；base 调 _handle_one 时同步可见）
        from app.models.sync_task import SyncTask as _ST
        sync_task = (
            db.query(_ST)
            .filter(_ST.sync_type == "collector", _ST.status == "running")
            .order_by(_ST.started_at.desc())
            .first()
        )
        sync_task_id = sync_task.id if sync_task else None

        result = self._upsert_asset(source, item, sync_task_id, db)
        return {result: 1}

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
