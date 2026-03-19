"""
Wazuh API 服务
"""

import httpx
from typing import Optional, List, Dict, Any
from app.core.config import settings


class WazuhClient:
    """Wazuh API 客户端"""

    def __init__(
        self,
        base_url: str = None,
        username: str = None,
        password: str = None
    ):
        self.base_url = base_url or settings.WAZUH_API_URL
        self.username = username or settings.WAZUH_API_USERNAME
        self.password = password or settings.WAZUH_API_PASSWORD
        self._token: Optional[str] = None
        self._client = httpx.Client(verify=False)  # Wazuh 使用自签名证书

    def _get_token(self) -> str:
        """获取或刷新 JWT token"""
        if not self._token:
            url = f"{self.base_url}/security/user/authenticate"
            response = self._client.post(
                url,
                auth=(self.username, self.password),
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            self._token = data["data"]["token"]
        return self._token

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, Any] = None,
        data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """发送请求到 Wazuh API"""
        token = self._get_token()
        url = f"{self.base_url}{endpoint}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        response = self._client.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=data
        )

        response.raise_for_status()
        return response.json()

    def get_agents(self) -> List[Dict[str, Any]]:
        """获取所有 agents"""
        data = self._request("GET", "/agents")
        return data.get("data", {}).get("affected_items", [])

    def get_agent_info(self, agent_id: str) -> Dict[str, Any]:
        """获取单个 agent 信息"""
        data = self._request("GET", f"/agents/{agent_id}")
        return data.get("data", {})

    def get_alerts(
        self,
        offset: int = 0,
        limit: int = 50,
        sort: str = "-timestamp",
        search: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """获取告警列表"""
        params = {
            "offset": offset,
            "limit": limit,
            "sort": sort
        }

        if search:
            for key, value in search.items():
                params[f"search_{key}"] = value

        data = self._request("GET", "/alerts/alerts", params=params)
        return data.get("data", {}).get("items", [])

    def get_alert(self, alert_id: str) -> Dict[str, Any]:
        """获取单个告警详情"""
        data = self._request("GET", f"/alerts/alerts/{alert_id}")
        return data.get("data", {})

    def get_alerts_by_agent(
        self,
        agent_id: str,
        offset: int = 0,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取指定 agent 的告警"""
        params = {
            "offset": offset,
            "limit": limit,
            "sort": "-timestamp"
        }
        data = self._request("GET", f"/agents/{agent_id}/alerts/summary", params=params)
        return data.get("data", {}).get("items", [])

    def get_syscheck(
        self,
        agent_id: str,
        offset: int = 0,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """获取 FIM (文件完整性监控) 事件"""
        params = {
            "offset": offset,
            "limit": limit,
            "sort": "-timestamp"
        }
        data = self._request("GET", f"/syscheck/{agent_id}", params=params)
        return data.get("data", {}).get("items", [])

    def close(self):
        """关闭客户端"""
        self._client.close()


# 全局 Wazuh 客户端实例
wazuh_client = WazuhClient()
