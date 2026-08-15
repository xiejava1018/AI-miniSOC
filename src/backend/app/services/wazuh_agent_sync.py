"""
Wazuh Agent 资产同步服务

将 Wazuh agents 同步到 soc_assets 表：
- 从 Wazuh API 获取所有 agents
- 转换为资产数据格式
- 通过 AssetSyncHandler 处理
"""

import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session

from app.services.wazuh_client import wazuh_client
from app.services.sync_handlers.asset_sync_handler import AssetSyncHandler

logger = logging.getLogger(__name__)


class WazuhAgentSyncService:
    """Wazuh Agent 资产同步服务"""

    def __init__(self, db: Session):
        self.db = db
        self.sync_handler = AssetSyncHandler()

    def sync_agents(self) -> Dict[str, Any]:
        """
        同步所有 Wazuh agents 到资产表

        Returns:
            同步结果统计
        """
        try:
            # 获取所有 Wazuh agents
            agents = wazuh_client.get_agents()
            logger.info(f"从 Wazuh 获取到 {len(agents)} 个 agents")

            # 转换为资产数据格式
            asset_items = self._convert_agents_to_assets(agents)

            # 使用 AssetSyncHandler 处理
            result = self.sync_handler.handle(
                source="wazuh",
                items=asset_items,
                db=self.db
            )

            logger.info(f"Wazuh Agent 同步完成: {result}")
            return result

        except Exception as e:
            logger.error(f"Wazuh Agent 同步失败: {e}")
            raise

    def _convert_agents_to_assets(self, agents: List[Dict]) -> List[Dict]:
        """
        将 Wazuh agent 数据转换为资产数据格式

        Wazuh Agent 数据结构：
        {
            "id": {"name": "agent-name", "ip": "x.x.x.x"},
            "status": "active/Disconnected",
            "name": "agent-name",
            "ip": "x.x.x.x",
            "os": {"name": "Ubuntu", "version": "22.04"},
            "dateAdd": "2023-01-01T00:00:00Z"
        }
        """
        assets = []

        for agent in agents:
            try:
                agent_info = agent.get("id", {})
                ip = agent_info.get("ip")
                name = agent_info.get("name")
                status = agent.get("status")

                if not ip:
                    logger.warning(f"Agent {name} 缺少 IP，跳过")
                    continue

                # 处理 IP 地址（Wazuh 可能返回 "any"）
                if ip == "any" or not ip:
                    continue

                # 获取 OS 信息
                os_obj = agent.get("os", {})
                os_name = os_obj.get("name", "Unknown")
                os_version = os_obj.get("version", "")

                # 确定网络区域（可以根据 IP 段判断）
                network_zone = self._determine_network_zone(ip)

                # 转换状态
                asset_status = "online" if status == "active" else "offline"

                asset_item = {
                    "asset_ip": ip,
                    "name": name,
                    "asset_status": asset_status,
                    "os_name": os_name,
                    "os_version": os_version,
                    "network_segment": "default",
                    "network_zone": network_zone,
                    "asset_type": "server",  # Wazuh agents 通常是服务器
                    "criticality": "medium",
                    "data_source": "wazuh",
                    "source_id": agent_info.get("id"),  # Wazuh agent ID
                    "wazuh_agent_id": agent_info.get("id"),
                    "asset_description": f"Wazuh Agent - {os_name} {os_version}".strip()
                }

                assets.append(asset_item)

            except Exception as e:
                logger.warning(f"转换 agent 数据失败: {e}, agent: {agent}")
                continue

        logger.info(f"成功转换 {len(assets)} 个 agents 为资产格式")
        return assets

    def _determine_network_zone(self, ip: str) -> str:
        """根据 IP 地址确定网络区域"""
        if ip.startswith("192.168.") or ip.startswith("10."):
            return "intranet"
        elif ip.startswith("172.16.") or ip.startswith("172.17.") or ip.startswith("172.18."):
            return "intranet"
        elif ip.startswith("8.") or ip.startswith("1.") or ip.startswith("114."):
            return "dmz"
        else:
            return "other"

    def sync_single_agent(self, agent_id: str) -> Dict[str, Any]:
        """
        同步单个 Wazuh agent

        Args:
            agent_id: Wazuh agent ID

        Returns:
            同步结果
        """
        try:
            # 获取 agent 详细信息
            agent_info = wazuh_client.get_agent_info(agent_id)
            logger.info(f"获取 agent {agent_id} 信息: {agent_info}")

            # 转换为资产格式
            assets = self._convert_agents_to_assets([agent_info])

            if not assets:
                return {"success": False, "message": "转换失败"}

            # 使用 AssetSyncHandler 处理
            result = self.sync_handler.handle(
                source="wazuh",
                items=assets,
                db=self.db
            )

            return {"success": True, "data": result}

        except Exception as e:
            logger.error(f"同步单个 agent 失败: {e}")
            return {"success": False, "message": str(e)}
