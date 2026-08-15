"""
Wazuh Inventory（应用清单/端口）OpenSearch 直查服务（M3/M4，2026-08-15）

设计依据：docs/design/2026-08-15-资产详情子域关联整改方案.md §3 M3（评审修订：直查不落库）
+ §8 POC 验证记录（P1-P5、P7）：
- 数据源：OpenSearch `wazuh-states-inventory-packages-*` / `wazuh-states-inventory-ports-*`
  （states 索引为状态快照语义，_id={agent_id}_{指纹}，无时间戳、无历史堆积）
- 单索引含全部 agent 文档（POC-4a：20 个 agent 混在 pve-ubuntu01 单索引），
  查询用通配 + {"term":{"agent.id": agent_id}} 过滤
- agent 内同包多文档为 deb+pypi 双安装方式的合法情况（0.7%，无需去重，带 type 列区分）
- 深翻页：单 agent 最大 ~3320 条 < max_result_window 10000（POC-3），limit 上限防御即可
- packages 字段：{name, version, size, type, path}（POC-1/P5）
- ports 字段：{source.port, network.transport, interface.state, process.name, process.pid}（POC-7）

复用 opensearch_scap_sync.py 的内联 httpx.Client 范式（项目中无独立 opensearch_client 模块）。
摘要卡 applications 计数：_count + 5 分钟内存缓存（避免详情页每次都打远端）。
"""

import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

PACKAGES_INDEX = "wazuh-states-inventory-packages-*"
PORTS_INDEX = "wazuh-states-inventory-ports-*"

# POC-3：深翻页防御（单 agent 实测最大 3320 < 10000，此处仅防御性上限）
MAX_LIMIT = 500
# 摘要卡计数缓存（方案 §3 M3：5 分钟）
COUNT_CACHE_TTL = 300


class WazuhInventoryService:
    """Wazuh states inventory 直查服务（应用清单 / 端口）"""

    def __init__(self):
        self._os = httpx.Client(
            base_url=settings.OPENSEARCH_URL.rstrip("/"),
            auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
            verify=False,  # Wazuh/OpenSearch 自签名证书
            timeout=30.0,
        )
        # {(agent_id, kind): (ts, count)}
        self._count_cache: Dict[tuple, tuple] = {}

    def close(self):
        self._os.close()

    # ------------------------------------------------------------------
    # 应用清单（packages）
    # ------------------------------------------------------------------

    def get_applications(
        self,
        agent_id: str,
        search: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        查询 agent 已安装软件包清单（当前状态快照）

        Returns:
            {"items": [{name, version, type, size, path}], "total": int}
        """
        limit = min(max(limit, 1), MAX_LIMIT)
        must: List[dict] = [{"term": {"agent.id": agent_id}}]
        if search:
            must.append({"wildcard": {"package.name": {"value": f"*{search.lower()}*"}}})

        body = {
            "size": limit,
            "from": skip,
            "query": {"bool": {"must": must}},
            "sort": [{"package.name": {"order": "asc", "unmapped_type": "keyword"}}],
            "_source": ["package.name", "package.version", "package.type", "package.size", "package.path"],
        }
        resp = self._os.post(f"/{PACKAGES_INDEX}/_search", json=body)
        resp.raise_for_status()
        data = resp.json()

        items = []
        for hit in data.get("hits", {}).get("hits", []):
            p = hit.get("_source", {}).get("package", {})
            items.append({
                "name": p.get("name"),
                "version": p.get("version"),
                "type": p.get("type"),
                "size": p.get("size") or 0,
                "path": p.get("path"),
            })

        total = data.get("hits", {}).get("total", {})
        return {"items": items, "total": total.get("value", 0) if isinstance(total, dict) else total}

    def count_applications(self, agent_id: str, use_cache: bool = True) -> int:
        """统计 agent 软件包数（摘要卡用，带 5 分钟缓存）"""
        cache_key = (agent_id, "packages")
        now = time.time()
        if use_cache:
            cached = self._count_cache.get(cache_key)
            if cached and now - cached[0] < COUNT_CACHE_TTL:
                return cached[1]

        resp = self._os.post(
            f"/{PACKAGES_INDEX}/_count",
            json={"query": {"term": {"agent.id": agent_id}}},
        )
        resp.raise_for_status()
        count = resp.json().get("count", 0)
        self._count_cache[cache_key] = (now, count)
        return count

    # ------------------------------------------------------------------
    # 端口（M4：本地 AssetPort 与 Wazuh states 双源合并的 Wazuh 侧数据源）
    # ------------------------------------------------------------------

    def get_ports(self, agent_id: str) -> List[Dict[str, Any]]:
        """
        查询 agent 监听端口（listening 状态快照，带进程信息）

        Returns:
            [{port, protocol, state, process, pid, local_ip}]
        """
        body = {
            "size": MAX_LIMIT,
            "query": {
                "bool": {
                    "must": [
                        {"term": {"agent.id": agent_id}},
                        {"term": {"interface.state": "listening"}},
                    ]
                }
            },
            "sort": [{"source.port": {"order": "asc", "unmapped_type": "long"}}],
            "_source": [
                "source.ip", "source.port", "network.transport",
                "interface.state", "process.name", "process.pid",
            ],
        }
        resp = self._os.post(f"/{PORTS_INDEX}/_search", json=body)
        resp.raise_for_status()
        hits = resp.json().get("hits", {}).get("hits", [])

        items = []
        for hit in hits:
            src = hit.get("_source", {})
            items.append({
                "port": src.get("source", {}).get("port"),
                "protocol": src.get("network", {}).get("transport"),
                "state": src.get("interface", {}).get("state"),
                "local_ip": src.get("source", {}).get("ip"),
                "process": src.get("process", {}).get("name"),
                "pid": src.get("process", {}).get("pid"),
            })
        return items
