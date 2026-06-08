"""
告警查询服务

数据源优先级:
1. OpenSearch (直接查 wazuh-alerts-4.x-* 索引,支持聚合查询)
2. Wazuh API (通过 WazuhClient 查询 agent 信息等)
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings

logger = logging.getLogger(__name__)

# wazuh-alerts-4.x-* 索引通配符
ALERTS_INDEX = "wazuh-alerts-4.x-*"


class AlertQueryService:
    """告警查询服务 - 双通道: OpenSearch + Wazuh API"""

    def __init__(self, db: Session):
        self.db = db
        self._os = httpx.Client(
            base_url=settings.OPENSEARCH_URL.rstrip("/"),
            auth=(settings.OPENSEARCH_USER, settings.OPENSEARCH_PASSWORD),
            verify=False,
            timeout=15,
        )

    # ── OpenSearch 公共方法 ──────────────────────────

    def _os_search(self, body: dict, index: str = None) -> dict:
        """执行 OpenSearch 查询"""
        idx = index or ALERTS_INDEX
        resp = self._os.post(
            f"/{idx}/_search",
            headers={"Content-Type": "application/json"},
            json=body,
        )
        resp.raise_for_status()
        return resp.json()

    # ── 告警列表 ─────────────────────────────────────

    def get_alerts(
        self,
        offset: int = 0,
        limit: int = 50,
        level: int = None,
        agent_id: str = None,
        start_time: datetime = None,
        end_time: datetime = None,
    ) -> Dict[str, Any]:
        """
        从 OpenSearch 查询告警列表，返回 {total, items}
        """
        must = []
        filters = []

        if level is not None:
            must.append({"range": {"rule.level": {"gte": level}}})

        if agent_id:
            must.append({"match": {"agent.id": agent_id}})

        if start_time or end_time:
            time_range = {}
            if start_time:
                time_range["gte"] = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            if end_time:
                time_range["lte"] = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            if time_range:
                filters.append({"range": {"@timestamp": time_range}})

        if must or filters:
            query = {"bool": {"must": must or [{"match_all": {}}], "filter": filters}}
        else:
            query = {"match_all": {}}

        body = {
            "query": query,
            "sort": [{"@timestamp": {"order": "desc"}}],
            "from": offset,
            "size": limit,
            "track_total_hits": True,
        }

        logger.debug("OpenSearch query: %s", body)
        result = self._os_search(body)
        total = result.get("hits", {}).get("total", {}).get("value", 0)
        hits = result.get("hits", {}).get("hits", [])
        return {
            "total": total,
            "items": self._normalize_alerts(hits),
        }

    def _normalize_alerts(self, hits: list) -> list:
        """将 OpenSearch hits 转为统一告警格式(与 Wazuh mock 结构兼容)"""
        alerts = []
        for h in hits:
            src = h.get("_source", {})
            alerts.append({
                "id": src.get("id") or h.get("_id"),
                "timestamp": src.get("@timestamp") or src.get("timestamp"),
                "rule": src.get("rule", {}),
                "agent": src.get("agent", {}),
                "location": src.get("location"),
                "full_log": src.get("full_log") or src.get("data", {}).get("alert", {}).get("signature"),
                "data": src.get("data"),
                "decoder": src.get("decoder"),
                "manager": src.get("manager"),
            })
        return alerts

    # ── 根据 IP 查询告警 ─────────────────────────────

    def get_alerts_by_ip(
        self,
        ip: str,
        offset: int = 0,
        limit: int = 50,
    ) -> Dict[str, Any]:
        body = {
            "query": {"match": {"agent.ip": ip}},
            "sort": [{"@timestamp": {"order": "desc"}}],
            "from": offset,
            "size": limit,
            "track_total_hits": True,
        }
        result = self._os_search(body)
        total = result.get("hits", {}).get("total", {}).get("value", 0)
        return {
            "total": total,
            "items": self._normalize_alerts(result.get("hits", {}).get("hits", [])),
        }

    # ── 单条告警详情 ──────────────────────────────────

    def get_alert_by_id(self, alert_id: str) -> Dict[str, Any]:
        body = {
            "query": {"ids": {"values": [alert_id]}},
            "size": 1,
        }
        result = self._os_search(body)
        hits = result.get("hits", {}).get("hits", [])
        if not hits:
            raise ValueError(f"告警不存在: {alert_id}")
        return self._normalize_alerts([hits[0]])[0]

    # ── 告警统计(OpenSearch 聚合) ────────────────────

    def get_alert_statistics(
        self,
        start_time: datetime = None,
        end_time: datetime = None,
    ) -> Dict[str, Any]:
        time_filter = {}
        if start_time or end_time:
            time_range = {}
            if start_time:
                time_range["gte"] = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            if end_time:
                time_range["lte"] = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            time_filter = {"range": {"@timestamp": time_range}}

        body = {
            "size": 0,
            "query": {"bool": {"filter": [time_filter]}} if time_filter else {"match_all": {}},
            "aggs": {
                "by_level": {"terms": {"field": "rule.level", "size": 20}},
                "by_agent": {"terms": {"field": "agent.name", "size": 10}},
                "by_description": {"terms": {"field": "rule.description", "size": 10}},
            },
        }
        result = self._os_search(body)
        aggs = result.get("aggregations", {})

        return {
            "by_level": [
                {"key": b["key"], "doc_count": b["doc_count"]}
                for b in aggs.get("by_level", {}).get("buckets", [])
            ],
            "by_agent": [
                {"key": b["key"], "doc_count": b["doc_count"]}
                for b in aggs.get("by_agent", {}).get("buckets", [])
            ],
            "by_description": [
                {"key": b["key"], "doc_count": b["doc_count"]}
                for b in aggs.get("by_description", {}).get("buckets", [])
            ],
        }

    # ── 告警趋势(date_histogram 聚合) ────────────────

    def get_alert_trend(
        self,
        hours: int = 24,
        interval_hours: int = 1,
    ) -> List[Dict[str, Any]]:
        now = datetime.utcnow()
        start_time = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

        body = {
            "size": 0,
            "query": {
                "bool": {
                    "filter": [{"range": {"@timestamp": {"gte": start_time}}}]
                }
            },
            "aggs": {
                "by_hour": {
                    "date_histogram": {
                        "field": "@timestamp",
                        "fixed_interval": f"{interval_hours}h",
                        "min_doc_count": 0,
                    },
                    "aggs": {
                        "critical": {
                            "filter": {"range": {"rule.level": {"gte": 12}}}
                        }
                    },
                }
            },
        }
        result = self._os_search(body)
        buckets = result.get("aggregations", {}).get("by_hour", {}).get("buckets", [])

        return [
            {
                "hour": b["key_as_string"],
                "total": b["doc_count"],
                "critical": b.get("critical", {}).get("doc_count", 0),
            }
            for b in buckets
        ]

    # ── 告警最多的资产 ────────────────────────────────

    def get_top_alert_assets(
        self,
        hours: int = 24,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        now = datetime.utcnow()
        start_time = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")

        body = {
            "size": 0,
            "query": {
                "bool": {
                    "filter": [{"range": {"@timestamp": {"gte": start_time}}}]
                }
            },
            "aggs": {
                "by_asset": {
                    "terms": {"field": "agent.ip", "size": limit},
                    "aggs": {
                        "critical": {
                            "filter": {"range": {"rule.level": {"gte": 12}}}
                        },
                        "last_alert": {
                            "max": {"field": "@timestamp"}
                        },
                    },
                }
            },
        }
        result = self._os_search(body)
        buckets = result.get("aggregations", {}).get("by_asset", {}).get("buckets", [])

        return [
            {
                "ip": b["key"],
                "alert_count": b["doc_count"],
                "critical_count": b.get("critical", {}).get("doc_count", 0),
                "last_alert_at": b.get("last_alert", {}).get("value_as_string", ""),
            }
            for b in buckets
        ]

    # ── Wazuh API 补充能力 ────────────────────────────

    def get_agent_list(self) -> List[Dict[str, Any]]:
        """从 Wazuh API 获取 agent 列表(补充资产信息)"""
        from app.services.wazuh_client import wazuh_client

        return wazuh_client.get_agents()

    def close(self):
        self._os.close()
