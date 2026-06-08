"""
Wazuh API 客户端

负责与 Wazuh API 交互，获取 agents、Vulnerability Detector、SCA 数据。
"""

import logging
from datetime import datetime
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)


class WazuhClient:
    """Wazuh API 客户端"""

    def __init__(
        self,
        base_url: str,
        username: str,
        password: str,
        verify_ssl: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self._token: Optional[str] = None
        self._token_expires: Optional[float] = None

    async def _get_token(self) -> str:
        """获取 JWT token（缓存到过期前）"""
        if self._token and self._token_expires:
            # _token_expires 是时间戳(float)，需要转换比较
            if datetime.now().timestamp() < self._token_expires:
                return self._token

        # Token 过期或不存在，重新获取
        logger.info("获取新的 Wazuh API token...")

        # 使用 HTTP Basic Auth 认证
        auth = httpx.BasicAuth(self.username, self.password)
        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.post(
                f"{self.base_url}/security/user/authenticate",
                auth=auth,
                headers={"Content-Type": "application/json"}
            )
            resp.raise_for_status()
            data = resp.json()
            self._token = data["data"]["token"]
            # Wazuh token 默认 12 小时有效，提前 5 分钟刷新，存为时间戳
            self._token_expires = datetime.now().timestamp() + 42700
            logger.info("Wazuh API token 获取成功")
            return self._token

    async def _request(
        self, method: str, endpoint: str, params: Optional[dict] = None
    ) -> dict:
        """发送认证请求"""
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(verify=self.verify_ssl) as client:
            resp = await client.request(
                method,
                f"{self.base_url}/{endpoint}",
                headers=headers,
                params=params,
            )

            # Token 过期时(401)自动清除并重试一次
            if resp.status_code == 401:
                logger.warning("Wazuh API token 已过期，重新获取...")
                self._token = None
                self._token_expires = None
                token = await self._get_token()
                headers = {"Authorization": f"Bearer {token}"}
                resp = await client.request(
                    method,
                    f"{self.base_url}/{endpoint}",
                    headers=headers,
                    params=params,
                )

            resp.raise_for_status()
            return resp.json()

    async def get_agents(self, limit: int = 500) -> list[dict]:
        """
        获取所有 Wazuh agents

        Args:
            limit: 最大返回数量

        Returns:
            Agent 列表，格式: [{"id": "000", "name": "...", "ip": "...", "status": "...", "os": {...}}, ...]
        """
        try:
            data = await self._request("GET", "agents", params={"limit": limit})
            # Wazuh API 返回 affected_items 而不是 items
            return data.get("data", {}).get("affected_items", [])
        except Exception as e:
            logger.error(f"获取 agents 失败: {e}")
            raise

    async def get_agent_info(self, agent_id: str) -> dict:
        """获取单个 agent 详细信息"""
        try:
            data = await self._request("GET", f"agents/{agent_id}")
            return data
        except Exception as e:
            logger.error(f"获取 agent {agent_id} 信息失败: {e}")
            raise

    async def get_agent_vulnerabilities(
        self, agent_id: str, limit: int = 100
    ) -> list[dict]:
        """
        获取 agent 的漏洞列表

        Args:
            agent_id: Agent ID
            limit: 最大返回数量

        Returns:
            漏洞列表
        """
        try:
            data = await self._request(
                "GET",
                f"vulnerability/{agent_id}",
                params={"limit": limit},
            )
            return data.get("data", {}).get("items", [])
        except Exception as e:
            logger.warning(f"获取 agent {agent_id} 漏洞失败: {e}")
            return []

    async def get_all_vulnerabilities(self, limit: int = 500) -> list[dict]:
        """获取所有漏洞（聚合所有 agent）"""
        try:
            agents = await self.get_agents()
            all_vulns = []
            for agent in agents:
                agent_id = agent.get("id")  # 扁平结构，直接获取 id
                if agent_id and agent.get("status") == "active":
                    vulns = await self.get_agent_vulnerabilities(agent_id, limit)
                    for vuln in vulns:
                        vuln["agent_id"] = agent_id
                        vuln["agent_name"] = agent.get("name")
                        vuln["agent_ip"] = agent.get("ip")
                    all_vulns.extend(vulns)
            return all_vulns
        except Exception as e:
            logger.error(f"获取所有漏洞失败: {e}")
            raise

    async def get_sca_results(self, agent_id: str) -> list[dict]:
        """
        获取 agent 的 SCA（Security Configuration Assessment）结果

        Args:
            agent_id: Agent ID

        Returns:
            SCA 检查项列表
        """
        try:
            data = await self._request("GET", f"sca/{agent_id}")
            return data.get("data", {}).get("items", [])
        except Exception as e:
            logger.warning(f"获取 agent {agent_id} SCA 结果失败: {e}")
            return []

    async def get_all_sca_results(self) -> list[dict]:
        """获取所有 SCA 结果（聚合所有 agent）"""
        try:
            agents = await self.get_agents()
            all_sca = []
            for agent in agents:
                agent_id = agent.get("id")  # 扁平结构，直接获取 id
                if agent_id and agent.get("status") == "active":
                    sca_items = await self.get_sca_results(agent_id)
                    for item in sca_items:
                        item["agent_id"] = agent_id
                        item["agent_name"] = agent.get("name")
                        item["agent_ip"] = agent.get("ip")
                    all_sca.extend(sca_items)
            return all_sca
        except Exception as e:
            logger.error(f"获取所有 SCA 结果失败: {e}")
            raise

    async def test_connection(self) -> bool:
        """测试 Wazuh API 连接"""
        try:
            await self._get_token()
            return True
        except Exception as e:
            logger.warning(f"Wazuh API 连接测试失败: {e}")
            return False
