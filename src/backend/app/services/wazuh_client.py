"""
Wazuh API 服务

T0（2026-08-15 脆弱性管理点亮计划）：
- 新增 `use_mock_data` 开关（构造参数，默认 False），供 /sync/wazuh?use_mock=true 冒烟使用；
- mock 模式下 get_agents / get_agent_info / get_vulnerabilities 返回 `mock_scap_data.MockSCAPDataGenerator`
  生成的模拟数据，不发真实请求；
- `get_vulnerabilities`：真实模式抛 NotImplementedError —— POC-1 已证实本环境 Wazuh API
  无 /vulnerability 路由（全 404），CVE 真实数据源为 OpenSearch `wazuh-states-vulnerabilities-*`，
  由 `services/opensearch_scap_sync.py`（T5）接管。
"""

import httpx
from typing import Optional, List, Dict, Any
from app.core.config import settings
from app.core.http_retry import RetryConfig, http_retry, RetryStats


class WazuhClient:
    """Wazuh API 客户端"""

    def __init__(
        self,
        base_url: str = None,
        username: str = None,
        password: str = None,
        use_mock_data: bool = False,
        retry_config: Optional[RetryConfig] = None,
    ):
        self.base_url = base_url or settings.WAZUH_API_URL
        self.username = username or settings.WAZUH_API_USERNAME
        self.password = password or settings.WAZUH_API_PASSWORD
        # T0: mock 开关（POST /vulnerabilities/sync/wazuh?use_mock=true 时置 True）
        self.use_mock_data = use_mock_data
        self._token: Optional[str] = None
        self._client = httpx.Client(verify=False)  # Wazuh 使用自签名证书
        # P3-T1：HTTP 重试配置
        self._retry_stats = RetryStats()
        self._retry_config = retry_config or RetryConfig.default()

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

    @http_retry()
    def _send_request(self, method: str, url: str, headers: dict, params: dict, data: dict):
        """单次发送请求（被 _request 调用，受重试装饰器保护，P3-T1）"""
        return self._client.request(
            method=method, url=url, headers=headers, params=params, json=data,
        )

    def _request(
        self,
        method: str,
        endpoint: str,
        params: Dict[str, Any] = None,
        data: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """发送请求到 Wazuh API（P3-T1：5xx/超时走 tenacity 重试）"""
        token = self._get_token()
        url = f"{self.base_url}{endpoint}"

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        response = self._send_request(
            method=method, url=url, headers=headers, params=params, data=data,
        )

        # Token 过期时(401)自动清除并重试一次
        if response.status_code == 401:
            self._token = None
            token = self._get_token()
            headers["Authorization"] = f"Bearer {token}"
            response = self._send_request(
                method=method, url=url, headers=headers, params=params, data=data,
            )

        response.raise_for_status()
        return response.json()

    @property
    def retry_stats(self) -> RetryStats:
        """P3-T1：返回本 client 累计重试统计（可观测）。"""
        return self._retry_stats

    def get_agents(self) -> List[Dict[str, Any]]:
        """获取所有 agents（mock 模式返回模拟 agent 列表）"""
        if self.use_mock_data:
            from app.services.mock_scap_data import MockSCAPDataGenerator
            return MockSCAPDataGenerator.get_all_agents()
        data = self._request("GET", "/agents")
        return data.get("data", {}).get("affected_items", [])

    def get_agent_info(self, agent_id: str) -> Dict[str, Any]:
        """获取单个 agent 信息（mock 模式返回模拟信息）"""
        if self.use_mock_data:
            from app.services.mock_scap_data import MockSCAPDataGenerator
            for agent in MockSCAPDataGenerator.get_all_agents():
                if agent.get("id") == agent_id:
                    return agent
            return {}
        data = self._request("GET", f"/agents/{agent_id}")
        return data.get("data", {})

    def get_vulnerabilities(
        self,
        agent_id: str,
        limit: int = 500
    ) -> List[Dict[str, Any]]:
        """
        获取指定 agent 的 SCAP（CVE）漏洞数据

        - mock 模式：返回 MockSCAPDataGenerator 生成的模拟漏洞（结构兼容
          wazuh_scap_sync._create_vulnerability_from_wazuh）；
        - 真实模式：POC-1（2026-08-15）证实本环境 Wazuh API 无 /vulnerability 路由
          （6 种变体全部 404），CVE 数据实际在 OpenSearch wazuh-states-vulnerabilities-*。
          真实同步由 services/opensearch_scap_sync.py 的 OpenSearchSCAPSyncService 接管，
          本方法不再尝试调用 Wazuh API。
        """
        if self.use_mock_data:
            from app.services.mock_scap_data import MockSCAPDataGenerator
            vulns = MockSCAPDataGenerator.generate_agent_vulnerabilities(agent_id)
            return vulns[:limit] if limit else vulns
        raise NotImplementedError(
            "本环境 Wazuh API 无 /vulnerability 端点（POC-1 证实 404）；"
            "真实 CVE 同步请使用 OpenSearchSCAPSyncService（services/opensearch_scap_sync.py）"
        )

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

    def get_agent_sysinfo(self, agent_id: str) -> Dict[str, Any]:
        """获取 agent 的系统信息（硬件、操作系统等）"""
        try:
            # 获取硬件信息
            data = self._request("GET", f"/syscollector/{agent_id}/hardware")
            return data.get("data", {})
        except Exception as e:
            logger = __import__("logging").getLogger(__name__)
            logger.error(f"Failed to get sysinfo for agent {agent_id}: {e}")
            return {}

    def close(self):
        """关闭客户端"""
        self._client.close()


# 全局 Wazuh 客户端实例
wazuh_client = WazuhClient()
