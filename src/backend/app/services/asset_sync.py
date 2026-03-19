"""
资产同步服务
从 Wazuh 同步 Agents 到资产表
"""

from sqlalchemy.orm import Session
from app.models import Asset
from app.services.wazuh_client import wazuh_client
import logging

logger = logging.getLogger(__name__)


class AssetSyncService:
    """资产同步服务"""

    def __init__(self, db: Session):
        self.db = db

    def sync_from_wazuh(self) -> dict:
        """从 Wazuh 同步资产"""
        try:
            # 获取 Wazuh agents
            agents = wazuh_client.get_agents()

            stats = {
                "total": len(agents),
                "created": 0,
                "updated": 0,
                "failed": 0
            }

            for agent in agents:
                try:
                    # 映射 Wazuh agent 到资产
                    asset_data = self._map_agent_to_asset(agent)
                    self._create_or_update_asset(asset_data)

                    if asset_data.get("is_new"):
                        stats["created"] += 1
                    else:
                        stats["updated"] += 1

                except Exception as e:
                    logger.error(f"同步 agent {agent.get('id')} 失败: {e}")
                    stats["failed"] += 1

            self.db.commit()
            logger.info(f"资产同步完成: {stats}")
            return stats

        except Exception as e:
            logger.error(f"资产同步失败: {e}")
            self.db.rollback()
            raise

    def _map_agent_to_asset(self, agent: dict) -> dict:
        """将 Wazuh agent 映射到资产模型"""
        agent_id = agent.get("id")
        ip = agent.get("ip")
        name = agent.get("name")
        status = agent.get("status")

        # 映射状态
        status_map = {
            "active": "在线",
            "disconnected": "离线",
            "never_connected": "从未连接"
        }
        asset_status = status_map.get(status, "未知")

        return {
            "name": name,
            "asset_ip": ip,
            "asset_type": "server",  # Wazuh agent 通常是服务器
            "asset_status": asset_status,
            "wazuh_agent_id": agent_id,
            "criticality": "medium",
            "asset_description": f"Wazuh Agent: {name}",
            "is_new": False  # 标记是否为新资产
        }

    def _create_or_update_asset(self, asset_data: dict):
        """创建或更新资产"""
        # 移除标记字段
        is_new = asset_data.pop("is_new", False)

        # 查找现有资产（通过 wazuh_agent_id 或 IP）
        asset = self.db.query(Asset).filter(
            (Asset.wazuh_agent_id == asset_data.get("wazuh_agent_id")) |
            (Asset.asset_ip == asset_data.get("asset_ip"))
        ).first()

        if asset:
            # 更新现有资产
            for key, value in asset_data.items():
                if value is not None:
                    setattr(asset, key, value)
        else:
            # 创建新资产
            asset = Asset(**asset_data)
            self.db.add(asset)
            is_new = True

        return asset

    def sync_single_asset(self, agent_id: str) -> Asset:
        """同步单个资产"""
        try:
            agent = wazuh_client.get_agent_info(agent_id)
            asset_data = self._map_agent_to_asset(agent)
            asset = self._create_or_update_asset(asset_data)
            self.db.commit()
            self.db.refresh(asset)
            return asset
        except Exception as e:
            logger.error(f"同步单个资产 {agent_id} 失败: {e}")
            self.db.rollback()
            raise
