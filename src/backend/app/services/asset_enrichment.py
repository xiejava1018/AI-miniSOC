"""
资产信息补充服务
从 Wazuh 获取资产的详细信息（操作系统、硬件等）
"""

import asyncio
import logging
from sqlalchemy.orm import Session
from app.models import Asset
from app.services.wazuh_client import wazuh_client

logger = logging.getLogger(__name__)


class AssetEnrichmentService:
    """资产信息补充服务"""

    def __init__(self, db: Session):
        self.db = db

    async def enrich_single_asset(self, asset_id: str):
        """补充单个资产的详细信息"""
        asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
        if not asset or not asset.wazuh_agent_id:
            logger.warning(f"Asset {asset_id} not found or no wazuh_agent_id")
            return

        try:
            # 异步获取系统信息
            sysinfo = await asyncio.to_thread(
                wazuh_client.get_agent_sysinfo,
                asset.wazuh_agent_id
            )

            # 更新操作系统信息
            if sysinfo.get("os"):
                os_data = sysinfo["os"]
                if os_data.get("name") and not asset.os_name:
                    asset.os_name = os_data["name"]
                if os_data.get("version") and not asset.os_version:
                    asset.os_version = os_data["version"]

            # 更新硬件信息
            hardware = {
                "cpu": sysinfo.get("cpu", {}),
                "memory": sysinfo.get("memory", {})
            }
            if not asset.hardware_info:
                asset.hardware_info = hardware

            # 更新同步时间
            from datetime import datetime, timezone
            asset.last_synced_at = datetime.now(timezone.utc)

            self.db.commit()
            logger.info(f"Successfully enriched asset {asset_id}")

        except Exception as e:
            logger.error(f"Failed to enrich asset {asset_id}: {e}")
            self.db.rollback()

    async def enrich_all_assets(self):
        """补充所有资产的详细信息"""
        assets = self.db.query(Asset).filter(
            Asset.wazuh_agent_id.isnot(None),
            Asset.data_source == "wazuh"
        ).all()

        logger.info(f"Starting enrichment for {len(assets)} assets")

        success_count = 0
        failed_count = 0

        for asset in assets:
            try:
                await self.enrich_single_asset(str(asset.id))
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to enrich asset {asset.id}: {e}")
                failed_count += 1

        logger.info(f"Enrichment completed: {success_count} success, {failed_count} failed")
        return {
            "total": len(assets),
            "success": success_count,
            "failed": failed_count
        }
