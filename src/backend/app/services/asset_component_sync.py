"""
资产组件（SBOM）同步服务（OH-1.4 方案3）

把 OpenSearch wazuh-states-inventory-packages-* 的软件包快照物化到
soc_asset_components（先删后插，per-asset 全量替换），供：
  - 本体对齐总览计数（asset-component 实例数）
  - 后续 CVE ↔ SBOM 漏洞匹配（降误报）

设计要点：
  - 纯同步 DB/OpenSearch IO 一律放 executor（§4.5 教训：不占 event loop）
  - per-asset 独立事务：单个 agent 失败不影响其他资产
  - states 索引是状态快照语义（无历史堆积），全量替换即正确口径
"""

import asyncio
import logging
from datetime import timedelta
from typing import List

from sqlalchemy import delete, select

from app.core.database import SessionLocal
from app.models.asset import Asset
from app.models.asset_component import AssetComponent
from app.services.wazuh_inventory_service import MAX_LIMIT, WazuhInventoryService

logger = logging.getLogger(__name__)

SYNC_INTERVAL_S = timedelta(hours=6).total_seconds()
_FIRST_RUN_DELAY = 180  # 避开启动高峰

_task: "asyncio.Task | None" = None


def _fetch_all_packages(svc: WazuhInventoryService, agent_id: str) -> List[dict]:
    """拉取 agent 全量软件包（分页翻完，MAX_LIMIT=500/页）"""
    items: List[dict] = []
    skip = 0
    while True:
        page = svc.get_applications(agent_id, skip=skip, limit=MAX_LIMIT)
        batch = page.get("items", [])
        items.extend(batch)
        total = page.get("total", 0)
        skip += len(batch)
        if not batch or skip >= total:
            break
    return items


def _sync_asset_components_sync() -> dict:
    """一轮全量同步（同步函数，调用方负责卸载到线程）"""
    db = SessionLocal()
    svc = WazuhInventoryService()
    stats = {"assets": 0, "components": 0, "failed": 0}
    try:
        assets = db.execute(
            select(Asset.id, Asset.wazuh_agent_id)
            .where(Asset.wazuh_agent_id.isnot(None))
        ).fetchall()
        db.rollback()  # 结束隐式只读事务，给 per-asset begin 腾位
        for aid, agent_id in assets:
            try:
                packages = _fetch_all_packages(svc, agent_id)
                with db.begin():
                    db.execute(
                        delete(AssetComponent).where(AssetComponent.asset_id == aid)
                    )
                    db.add_all([
                        AssetComponent(
                            asset_id=aid,
                            agent_id=agent_id,
                            name=p["name"] or "unknown",
                            version=p.get("version"),
                            component_type=p.get("type") or "other",
                            size=p.get("size"),
                            path=p.get("path"),
                        )
                        for p in packages
                    ])
                stats["assets"] += 1
                stats["components"] += len(packages)
            except Exception:
                stats["failed"] += 1
                logger.exception("sync components failed asset=%s agent=%s", aid, agent_id)
        logger.info("asset component sync done: %s", stats)
        return stats
    finally:
        svc.close()
        db.close()


async def run_component_sync_once() -> dict:
    """手动/调度触发一轮同步（IO 卸载到线程）"""
    return await asyncio.to_thread(_sync_asset_components_sync)


async def _loop() -> None:
    logger.info("asset component sync loop started (interval=6h)")
    await asyncio.sleep(_FIRST_RUN_DELAY)
    while True:
        try:
            await run_component_sync_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("asset component sync iteration failed")
        await asyncio.sleep(SYNC_INTERVAL_S)


def start_asset_component_scheduler() -> None:
    """启动 SBOM 同步后台任务（幂等；ASSET_COMPONENT_SYNC_ENABLED=false 可关）"""
    global _task
    import os
    if os.environ.get("ASSET_COMPONENT_SYNC_ENABLED", "true").lower() != "true":
        logger.info("asset component sync disabled by env")
        return
    if _task is not None and not _task.done():
        return
    _task = asyncio.create_task(_loop())
    logger.info("asset component sync task started")


async def stop_asset_component_scheduler() -> None:
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
