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

import logging
from typing import Optional, List, Dict, Any

import httpx

from app.core.config import settings
from app.core.http_retry import RetryConfig, http_retry, RetryStats

logger = logging.getLogger(__name__)


class WazuhClient:
    """Wazuh API 客户端"""

    @staticmethod
    def _resolve_config(db: Optional[object]) -> Optional[Dict[str, Any]]:
        """从 DataSourceResolver 解析 Wazuh 配置；失败/无 DB 一律返回 None（回落 settings）。"""
        if db is None:
            return None
        try:
            from app.services.data_source_resolver import data_source_resolver

            rc = data_source_resolver.resolve("wazuh", db)
            return rc.config if rc and rc.config else None
        except Exception as e:
            logger.warning("DataSourceResolver 读 wazuh 失败（fallback env）: %s", e)
            return None

    def __init__(
        self,
        base_url: str = None,
        username: str = None,
        password: str = None,
        use_mock_data: bool = False,
        retry_config: Optional[RetryConfig] = None,
        db: Optional[object] = None,
    ):
        # 配置中心 v1（X1E-11）：如果未显式传参，尝试从 DataSourceResolver 读取；
        # 解析失败一律回落 settings，保持向后兼容。
        resolved = self._resolve_config(db)
        self.base_url = (
            base_url
            or (resolved.get("endpoint") if resolved else None)
            or settings.WAZUH_API_URL
        )
        self.username = (
            username
            or (resolved.get("username") if resolved else None)
            or settings.WAZUH_API_USERNAME
        )
        self.password = (
            password
            or (resolved.get("password") if resolved else None)
            or settings.WAZUH_API_PASSWORD
        )
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
            # 2026-10-13 拦截：凭据 None / 空 → 抛 WazuhConfigError
            # 不要让 httpx 内部拼 auth=(None, None) 才报 TypeError。
            # 上游 catch 精确异常可提示运维检查配置，而不是看作网络问题。
            if not self.username or not self.password:
                raise WazuhConfigError(
                    "Wazuh 凭据未配置（WazuhClient.username/password 为 None）。"
                    "请检查 (1) soc_data_sources 表 type=wazuh 记录且 is_default=true "
                    "且 enabled=true； (2) WazuhClient 实例化时是否传 db；"
                    " (3) settings.WAZUH_API_USERNAME/PASSWORD 或 .env 兑底；"
                    " (4) fernet 密钥与 DB 密文是否匹配。"
                )
            url = f"{self.base_url}/security/user/authenticate"
            try:
                response = self._client.post(
                    url,
                    auth=(self.username, self.password),
                    headers={"Content-Type": "application/json"},
                )
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
                raise WazuhNetworkError(f"Wazuh API 网络不可达: {e}") from e
            except httpx.HTTPError as e:
                # transport-level error（SSL/协议错误）
                raise WazuhNetworkError(f"Wazuh API 传输错误: {e}") from e

            if response.status_code == 401:
                # Wazuh 明确拒绝凭据 → WazuhAuthError
                try:
                    detail = response.json().get("detail", response.text[:200])
                except Exception:
                    detail = response.text[:200]
                raise WazuhAuthError(
                    f"Wazuh API 401 拒绝认证: {detail}。请检查 wazuh 用户密码"
                    f"（soc_data_sources 表或 .env WAZUH_API_PASSWORD）。"
                )
            try:
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                raise WazuhNetworkError(f"Wazuh API HTTP {e.response.status_code}: {e}") from e

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

    # ---- OH-6.6（OH-3.9/端点行为图数据源扩展，2026-10-07） ----

    def get_processes(
        self, agent_id: str, limit: int = 500
    ) -> List[Dict[str, Any]]:
        """syscollector 进程清单（端点行为图 creates 边数据源）。

        实测注（2026-10-07）：本环境部分 agent 的 syscollector 存在“毒记录”
        ——含该记录的任何分页窗都 400。调用方须按 agent 捕获异常降级。
        """
        data = self._request(
            "GET", f"/syscollector/{agent_id}/processes",
            params={"limit": limit, "offset": 0},
        )
        return data.get("data", {}).get("affected_items", [])

    def get_ports(
        self, agent_id: str, limit: int = 500
    ) -> List[Dict[str, Any]]:
        """syscollector 监听端口清单（本地监听，非外联连接）。"""
        data = self._request(
            "GET", f"/syscollector/{agent_id}/ports",
            params={"limit": limit, "offset": 0},
        )
        return data.get("data", {}).get("affected_items", [])

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


# ──────────────────────────────────────────────────────────────────
# 异常类型分级（2026-10-13 资产稽核 TypeError 后增加）
#
# 调用方可以 catch 精确类型，避免把所有 WazuhClient 异常都包成
# 含义模糊的"Wazuh API 不可达"。三级区分：
#
#   WazuhConfigError    → 配置读取失败：httpx auth=(None, None) / fernet
#                          key 错 / soc_data_sources 表无 wazuh 记录
#                          （本项目的 2026-10-13 事故是这一类）
#   WazuhAuthError      → Wazuh 主动拒绝：401 / 用户名密码错 / JWT 过期
#                          且刷新失败
#   WazuhNetworkError   → 网络问题：连接超时 / TCP RST / DNS 失败 /
#                          Wazuh 服务器不可达
#
# 上游（如 asset_reconciliation）应当按顺序 catch：WazuhConfigError
# 要独立提示运维"检查 soc_data_sources 表和 fernet key"，不能混为
# "Wazuh 不可达"。
# ──────────────────────────────────────────────────────────────────


class WazuhClientError(RuntimeError):
    """WazuhClient 调用过程异常的基类。"""


class WazuhConfigError(WazuhClientError):
    """配置读取失败（DataSourceResolver / settings 均为 None 或解密失败）。

    修复路径：
      1. 检查 soc_data_sources 表是否有 type=wazuh 的启用 + is_default 记录
      2. 如果 .env 兑底：检查 src/backend/.env 是否有
         WAZUH_API_USERNAME / WAZUH_API_PASSWORD
      3. 如果走 DB：检查 fernet 密钥与加密值是否匹配
    """


class WazuhAuthError(WazuhClientError):
    """Wazuh API 主动拒绝认证（HTTP 401）。

    修复路径：
      1. 验证 Wazuh API 上的 wazuh 用户密码是否变更
      2. 如果走了 DB：last_test_at 与 last_test_ok 状态
      3. JWT 过期且重试仍 401 → 可能 wazuh 服务本身被重置过
    """


class WazuhNetworkError(WazuhClientError):
    """Wazuh API 网络问题（连接超时 / TCP RST / DNS 失败）。

    修复路径：
      1. telnet https://<wazuh>:55000 验证端口可达
      2. 看 wazuh-collector 容器是否在跑（业务采集是否成功）
    """


# 全局 Wazuh 客户端实例
#
# 【2026-10-13 告警】该单例在模块 import 时创建，WazuhClient.__init__
# 接受 db 参数默认 None。_resolve_config(db=None) 立刻 return None →
# DataSourceResolver 路径失效，配置中心 v1 (soc_data_sources 表) 在该单例
# 上永远不生效，凭据走 settings 兑底。
#
# 实际后果：环境变量 WAZUH_API_USERNAME/PASSWORD 未配置时，httpx
# auth=(None, None) 拼出 TypeError "sequence item 0: expected a
# bytes-like object, NoneType found"，表面看是"Wazuh API 不可达"，实际
# 是配置读取错误。
#
# 现状：2026-10-13 .env 已补 WAZUH_API_USERNAME/PASSWORD 兑底，能跑。
# 架构债务：11+ 调用点共用此单例，配置中心 v1 在这里静默失效。
# 修正方向（未在本次 PR）：引入 get_wazuh_client(db=None) 工厂函数
# 取代这个单例，所有调用点改为 get_wazuh_client(db=...) 让 db 透传。
# 跟踪：见 docs/sessions/2026-10-13-asset-reconciliation-wazuh-typeerror.md
#
# 过渡期豁免：允许本单例继续走 settings 兑底，调用方需自行保证 .env
# 有 WAZUH_API_USERNAME/PASSWORD 或上游代码已传 db。
wazuh_client = WazuhClient()


# ──────────────────────────────────────────────────────────────────
# 2026-10-13 lazy 单例代理（保留旧 wazuh_client 名字供向后兼容）
#
# 问题：wazuh_client 在 import 时创建，db=None，凭据永远走 .env 兑底，
# 11+ 调用点共用这个被配置中心旁路的单例。
#
# 方案：新增 get_wazuh_client(db=None) 工厂，让调用点可选性传 db；
# 11+ 旧调用点可逐步迁移过去，老接口 wazuh_client 继续可用。
# 该代理走 _LazyWazuhClientSingleton，调用 .get_agents() 等方法时
# 才检查是否有 db 可用。
#
# 现状：现有 11+ 调用点不变仍走 wazuh_client（.env 兑底）；新代码
# 应当用 get_wazuh_client(db=...) 走配置中心 v1。
# ──────────────────────────────────────────────────────────────────
import threading
import time

_wazuh_client_singleton: Optional["WazuhClient"] = None
_wazuh_client_lock = threading.Lock()
_wazuh_client_created_with_db: bool = False
_wazuh_client_created_at: float = 0.0

# 与 DataSourceResolver._CACHE_TTL 对齐：单例超过该时长且调用方带 db 时
# 重建，让 soc_data_sources 的配置变更（改密码/换 endpoint）在 ≤60s 内
# 生效；不重建的场景（无 db 调用）继续用旧单例，避免每请求 new
# httpx.Client 的连接池抖动。
_WAZUH_CLIENT_TTL_SECONDS = 60.0


def get_wazuh_client(
    db: Optional[object] = None,
    use_mock_data: bool = False,
) -> "WazuhClient":
    """获取 WazuhClient 单例，支持 db 透传走配置中心 v1。

    语义（2026-10-13 v2，修 "首次固化" 雷）：
    - 单例不存在 → 用当前参数创建
    - 调用方传 db 但现有单例是 "无 db" 创建的 → 关旧建新（升级到配置中心路径）
    - 调用方传 db 且单例存活超过 _WAZUH_CLIENT_TTL_SECONDS → 关旧建新
      （让 soc_data_sources 配置变更 ≤ 60s 生效；resolver 自身也有 60s
      缓存，两层对齐）
    - 其余情况 → 复用现有单例（无 db 调用方不触发重建，避免降级）

    线程注意：不要在 asyncio.to_thread 的工作线程里首次传 db 建单例并
    把外层 session 带进 resolver 查询——SQLAlchemy session 非线程安全。
    调用方应在事件循环线程先 get_wazuh_client(db=...)，再把 client 方法
    丢进 to_thread（参考 asset_enrichment 的用法）。

    调用方迁移路径：
      旧：from app.services.wazuh_client import wazuh_client
          wazuh_client.get_agents()
      新：from app.services.wazuh_client import get_wazuh_client
          get_wazuh_client(db=db).get_agents()
    """
    global _wazuh_client_singleton, _wazuh_client_created_with_db, _wazuh_client_created_at
    with _wazuh_client_lock:
        need_create = False
        if _wazuh_client_singleton is None:
            need_create = True
        elif db is not None and not _wazuh_client_created_with_db:
            # 升级路径：旧单例是 env 兑底建的，现在有 db 了 → 重建走配置中心
            need_create = True
        elif db is not None and (time.monotonic() - _wazuh_client_created_at) > _WAZUH_CLIENT_TTL_SECONDS:
            # TTL 路径：让配置中心变更 <=60s 生效
            need_create = True

        if need_create:
            old = _wazuh_client_singleton
            _wazuh_client_singleton = WazuhClient(db=db, use_mock_data=use_mock_data)
            _wazuh_client_created_with_db = db is not None
            _wazuh_client_created_at = time.monotonic()
            if old is not None:
                try:
                    old.close()
                except Exception:  # noqa: BLE001 — 关旧实例失败不影响新单例
                    pass
        return _wazuh_client_singleton


def _reset_wazuh_client_singleton_for_tests() -> None:
    """仅供单测调用：重置 lazy 单例。生产代码不应调用。"""
    global _wazuh_client_singleton, _wazuh_client_created_with_db, _wazuh_client_created_at
    with _wazuh_client_lock:
        old = _wazuh_client_singleton
        _wazuh_client_singleton = None
        _wazuh_client_created_with_db = False
        _wazuh_client_created_at = 0.0
        if old is not None:
            try:
                old.close()
            except Exception:
                pass

