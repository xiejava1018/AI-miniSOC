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
from app.services.network_segment import infer_segment
from app.services.sync_handlers.base import BaseSyncHandler
from app.services.attribution_service import AttributionReviewService
from app.services.identity_fusion import score_fusion

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
    # P3：scanner 两个通道的预期间隔按【调度节奏】而非采集器心跳定——
    # 心跳 30s 只证明扫描器活着；数据推送只在任务完成时发生，
    # central_scan_scheduler 每天 03:00/04:00 建任务，实际节奏≈每天一次。
    # 按 300s 判定会让 scanner:ports 一天里 23+ 小时显示“过期”（假 degraded）。
    # 90000s = 25h（24h 调度 + 1h 缓冲），超过一个调度周期没跑才标 degraded。
    "scanner": 90000,
    "scanner-port": 90000,
}

# Asset 模型上允许 Collector 写入的字段白名单
# T4（决策1，2026-08-15）：移除 criticality —— 关键度是业务属性，
# 只能由安全运营人工维护（资产页/手动提升），采集器无权覆盖；
# 否则 TP-Link 每 5 分钟推送会把回填后的 medium 覆盖回旧值。
#
# network_zone 不在白名单：sync 路径不允许 collector 覆盖该字段。
# 原因（2026-XX-XX 修复）：tplink/wazuh 老 inventory 上报 intranet/other 这些老 5 值，
# update 路径会试图覆盖人工回填的合法自定义值（lan-main / lan-199 等），触发 CHECK 冲突。
# 只在 _create_new 路径以收敛后的 8 值初始化新资产；现有资产 network_zone
# 始终是人工/迁移/脚本设置的权威值，collector 不动。
_UPDATABLE_FIELDS = {
    "name", "asset_type", "asset_status", "mac_address",
    # "network_zone" 故意从白名单移除（见上注释）
    "asset_description",
    "data_source", "os_name", "os_version", "wazuh_agent_id",
}


# network_zone 收敛映射表（详见 docs/design/network-zone-redesign.md）：
#   老 5 值 → 8 值映射，防止 tplink / wazuh 老 inventory 上报老枚举值
#   触发 soc_assets_network_zone_check CHECK 拖选1 冲突。
#
#   未在映射表里的非法值返回 None（调用方决策），
#   以保留人工/脚本手动填过的 lan-main / lan-199 等不在 8 值白名单内的自定义值。
_OLD_ZONE_TO_NEW = {
    "intranet":  "production",  # 老 5 值：内网 → 生产内网
    "dmz":       "dmz",         # 老值仍在 8 值白名单，保持
    "office":    "office",
    "management": "management",
    "other":     "unknown",     # 老任意填兜底 → 未分类（需人工复核）
}

_NEW_ZONES = frozenset({"public", "dmz", "production", "office", "dev", "management", "isolated", "unknown"})


def _normalize_network_zone(value) -> str | None:
    """同步路径的 network_zone 收敛函数（create + update 都用）。

    策略：
      - None / 空字符串 → None（调用方不更新该字段）
      - 已在 8 值白名单 → 原样返回
      - 老 5 值枚举（intranet/other/...）→ 映射到新 8 值
      - 其他非空字符串（如用户自定义的 lan-199 / lan-main）→ 原样返回
        （避免覆盖人工回填过的 lan-main / lan-199 等合法但不在 8 值白名单的值）
      - 唯一的危险源：collector 上报的、未在映射表、不在白名单、且非空的字符串——
        这种应该有人工复核，不在 sync 阶段硬收敛（保持数据真实性，依赖 CHECK 拒写入）。

    返回值：
      - 合法且白名单内的字符串 → 原样
      - 老 5 值 → 映射后的字符串
      - None / 空字符串 → None
      - 非法但非空 → 原样字符串（让 DB CHECK 报拖选1 冲突触发人工干预）
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if s in _NEW_ZONES:
        return s
    if s in _OLD_ZONE_TO_NEW:
        return _OLD_ZONE_TO_NEW[s]
    # 不在白名单也不在映射表（如用户自定义的 lan-main / lan-199）——原样返回
    return s


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

        # 2026-10-08：wazuh_agent_id 漂移识别
        # 背景：partial unique index 让 wazuh_agent_id 全局唯一。Wazuh agent DHCP 漂移到新 IP
        # 之后，旧 IP 被 tplink 等其他来源接管时，旧资产上 wazuh_agent_id 残留，
        # 阻止新 IP 的资产重新入表 → UniqueViolation → 同 batch 后续 17 条全部 500。
        # 修复：先释放“陈旧占位”，再走原有查重+upsert。
        if item.get("wazuh_agent_id"):
            self._release_stale_wazuh_agent_id(item, db)

        # segment 优先级：采集器显式上报 > 环境事实表推断（app/services/network_segment.py）
        # 背景（2026-XX-XX）：存量资产已从 'default' 回填为 hq-lan/aliyun-172.18 等，
        # 若继续用裸 'default' 查重，(default, ip) 必然 miss → 每 5 分钟批量建重复资产。
        network_segment = item.get("network_segment") or infer_segment(asset_ip)

        existing: Optional[Asset] = db.query(Asset).filter(
            Asset.asset_ip == asset_ip,
            Asset.network_segment == network_segment,
        ).first()

        if not existing:
            # fallback：按 IP 查全部 segment，防“台账已被人工/回填改成非推断 segment”场景。
            # 命中规则：
            #   - 恰好 1 条 → 同一台（IP 全局唯一），走更新；
            #   - 多条中有 segment == 推断值 → tplink/wazuh 上报的就是那个网段的设备，走更新；
            #   - 多条且推断值不在其中 → 真多网段同 IP，保持 None 走新建（撞唯一约束会入死信，人工处理）。
            by_ip = db.query(Asset).filter(Asset.asset_ip == asset_ip).all()
            if len(by_ip) == 1:
                existing = by_ip[0]
            else:
                existing = next((a for a in by_ip if a.network_segment == network_segment), None)

        now = datetime.now(timezone.utc)

        if existing:
            return self._update_existing(existing, source, item, sync_task_id, now, db)

        # OH-4.1：IP 未命中，不立刻新建——先按其他身份信号（MAC/wazuh agent/主机名）
        # 查候选并做融合判定，避免 DHCP 漂移/改名场景下产生重复资产。
        fused = self._try_identity_fusion(item, source, sync_task_id, now, db)
        if fused is not None:
            return fused

        return self._create_new(source, item, sync_task_id, now, db)

    def _release_stale_wazuh_agent_id(self, item: dict, db: Session) -> None:
        """释放被“陈旧资产”占用的 wazuh_agent_id。

        背景：partial unique index `uq_soc_assets_agent_id` 让 wazuh_agent_id 在
        soc_assets 表里全局唯一（NULL 例外）。当 Wazuh agent DHCP 漂移到新 IP、
        且旧 IP 被 tplink / scanner / 人工等其他来源接管后，旧资产上 wazuh_agent_id
        会残留 → 阻止新 IP 的资产重新入表 → UniqueViolation → 同 batch 后续 N 条全 500。

        判定“陈旧”：
          - asset_status == 'offline'           （wazuh 那边已断连）
          - last_synced_at 早于 24h              （wazuh 那边已很久没推）
          - data_source != 'wazuh'              （已经被其他来源接管）

        “自己”判定（不释放）：
          - 占用资产的 IP == 新 item IP
          - 且 data_source 仍是 wazuh 或为 None
          （不依赖 network_segment：Wazuh 采集器可能不报 segment 或报不一致）

        不释放“陈旧”的：
          - 则 raise（采集器侧需人工介入）

        调用时机：_upsert_asset 入口。
        """
        agent_id = str(item.get("wazuh_agent_id"))
        target_ip = item.get("asset_ip")

        stale = db.query(Asset).filter(
            Asset.wazuh_agent_id == agent_id,
        ).first()
        if stale is None:
            return  # 无占用，无需释放

        # “自己”判定：同 IP + 是 wazuh 资产/未确定源 → 更新路径不冲突，不释放
        # 不依赖 network_segment：Wazuh 采集器现在 transformers.py 写死 'default'，
        # 但库中资产可能是 lan-main / aliyun-172.18 等真实段，segment 不一致是常态。
        if str(stale.asset_ip) == str(target_ip) and stale.data_source in (None, "wazuh"):
            return

        now = datetime.now(timezone.utc)
        is_stale = (
            stale.asset_status == "offline"
            or (stale.last_synced_at is not None
                and (now - stale.last_synced_at).total_seconds() > 86400)
            or (stale.data_source is not None and stale.data_source != "wazuh")
        )

        if not is_stale:
            # 占用方还是“活着的 wazuh 资产” → 采集器侧 wazuh_agent_id 重复上报，不该发生
            raise ValueError(
                f"wazuh_agent_id {agent_id} 已被活跃资产 {stale.id} (ip={stale.asset_ip}) 占用，"
                f"无法新建/更新 {target_ip}；请检查 Wazuh Server 上是否有重复 agent id"
            )

        # 释放占位：设为 NULL 让 partial unique index 跳过，变更日志记录
        stale.wazuh_agent_id = None
        db.flush()
        self._log_change(
            asset_id=stale.id, sync_task_id=None,
            change_type="wazuh_agent_id_drop",
            field_name="wazuh_agent_id",
            old_value=agent_id, new_value=None, db=db,
        )
        logger.info(
            "OH-4.1 wazuh_agent_id 漂移识别：释放旧资产 %s (ip=%s) 上的 wazuh_agent_id=%s，"
            "新观测将绑定到 %s",
            stale.id, stale.asset_ip, agent_id, target_ip,
        )

    def _find_fusion_candidates(self, item: dict, db: Session) -> list:
        """按非 IP 身份信号查候选资产（MAC / wazuh agent / 主机名）。"""
        q = db.query(Asset)
        conditions = []
        mac = item.get("mac_address")
        if mac:
            conditions.append(Asset.mac_address == mac)
        agent_id = item.get("wazuh_agent_id")
        if agent_id:
            conditions.append(Asset.wazuh_agent_id == str(agent_id))
        hostname = item.get("name")
        if hostname:
            conditions.append(Asset.name == hostname)
        if not conditions:
            return []
        from sqlalchemy import or_
        return q.filter(or_(*conditions)).limit(20).all()

    def _try_identity_fusion(
        self, item: dict, source: str, sync_task_id, now: datetime, db: Session
    ) -> Optional[str]:
        """身份信号融合判定。

        返回：
            "updated"  —— auto_merge，已合并到候选资产；
            "skipped"  —— needs_review，保守不新建（记录日志，待确认工作台）；
            None       —— distinct/无候选，调用方走新建。
        """
        candidates = self._find_fusion_candidates(item, db)
        if not candidates:
            return None

        # 逐个候选评分，取置信度最高者
        best = None
        best_result = None
        scored = []
        for cand in candidates:
            res = score_fusion(item, cand)
            scored.append((cand, res))
            if best_result is None or res.confidence > best_result.confidence:
                best, best_result = cand, res

        if best_result.decision == "auto_merge":
            logger.info(
                "OH-4.1 身份融合自动合并：观测 IP=%s → 资产 %s（confidence=%.2f）",
                item.get("asset_ip"), best.asset_ip, best_result.confidence,
            )
            return self._update_existing(best, source, item, sync_task_id, now, db, allow_ip_update=True)

        if best_result.decision == "needs_review":
            # 保守安全动作：不自动新建（防重复资产），落 OH-UI.3 确认工作台
            # 待人工裁决；同观测重复触发只 bump 计数。落表失败不应阻断同步主流程，
            # 记 error 后仍按 skipped 处理（下一轮可再次触发）。
            logger.warning(
                "OH-4.1 融合待复核，已暂停自动新建：观测 IP=%s ↔ 候选 %s"
                "（confidence=%.2f，冲突因子=%s）",
                item.get("asset_ip"), best.asset_ip,
                best_result.confidence, best_result.conflict_factors,
            )
            try:
                AttributionReviewService(db).create_or_bump_review(
                    item=item, source=source, sync_task_id=sync_task_id,
                    candidates_scored=scored, best=(best, best_result), now=now,
                )
            except Exception:  # noqa: BLE001
                logger.error(
                    "OH-UI.3 待复核落表失败：观测 IP=%s 候选=%s",
                    item.get("asset_ip"), best.asset_id, exc_info=True,
                )
            return "skipped"

        return None


    def _create_new(self, source: str, item: dict, sync_task_id, now: datetime, db: Session) -> str:
        # 新建资产的 segment：显式上报优先，否则按环境事实表推断（不再硬编码 'default'）
        if not item.get("network_segment"):
            item["network_segment"] = infer_segment(item.get("asset_ip"))

        # 8 值方案（详见 docs/design/network-zone-redesign.md）：
        # 收敛老 5 值为新 8 值（intranet→production 等），
        # 白名单内值原样，调用 _normalize_network_zone()。
        normalized = _normalize_network_zone(item.get("network_zone"))
        if normalized is not None:
            item["network_zone"] = normalized
        else:
            item.pop("network_zone", None)  # 未上报则不写字段，避免 CHECK 拖选1 冲突

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

    def _update_existing(self, asset: Asset, source: str, item: dict, sync_task_id, now: datetime, db: Session, allow_ip_update: bool = False) -> str:
        changed_fields = []

        # OH-4.1 融合合并：身份证据（MAC/agent）一致但 IP 漂移时，允许同步 IP。
        if allow_ip_update:
            new_ip = item.get("asset_ip")
            if new_ip and str(new_ip) != str(asset.asset_ip):
                old_ip = str(asset.asset_ip)
                asset.asset_ip = new_ip
                changed_fields.append(("asset_ip", old_ip, str(new_ip)))

        for field in _UPDATABLE_FIELDS:
            new_value = item.get(field)
            if new_value is None:
                continue
            old_value = getattr(asset, field, None)
            old_str = str(old_value) if old_value is not None else None
            new_str = str(new_value) if not isinstance(new_value, str) else new_value
            if old_str != new_str:
                logger.info(f"Field {field}: {old_str} -> {new_str}")
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
