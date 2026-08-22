"""
告警查询服务

数据源优先级:
1. OpenSearch (直接查 wazuh-alerts-4.x-* 索引,支持聚合查询)
2. Wazuh API (通过 WazuhClient 查询 agent 信息等)
"""

import logging
from datetime import datetime, timedelta, timezone
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
        self._srcip_field_cached = None
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
        sort_by: str = None,
        sort_order: str = None,
    ) -> Dict[str, Any]:
        """
        从 OpenSearch 查询告警列表，返回 {total, items}

        Args:
            sort_by: 排序字段，支持 'timestamp' (默认) 或 'level'
            sort_order: 排序方向，'asc' 或 'desc'
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

        # 构建排序
        if sort_by == "level":
            # 按等级排序
            order = sort_order or "desc"
            sort_clause = [{"rule.level": {"order": order, "missing": "_last"}}]
        else:
            # 默认按时间戳排序
            order = sort_order if sort_order in ["asc", "desc"] else "desc"
            sort_clause = [{"@timestamp": {"order": order}}]

        body = {
            "query": query,
            "sort": sort_clause,
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
        sort_by: str = None,
        sort_order: str = None,
    ) -> Dict[str, Any]:
        # 构建排序
        if sort_by == "level":
            order = sort_order or "desc"
            sort_clause = [{"rule.level": {"order": order, "missing": "_last"}}]
        else:
            order = sort_order if sort_order in ["asc", "desc"] else "desc"
            sort_clause = [{"@timestamp": {"order": order}}]

        body = {
            "query": {"match": {"agent.ip": ip}},
            "sort": sort_clause,
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

    # ── 精确分级计数（服务端聚合）─────────────────────

    # Wazuh rule.level 标准阈值（与 report_generator.py 一致）
    LEVEL_CRITICAL = 13
    LEVEL_HIGH = 10
    LEVEL_MEDIUM = 7
    LEVEL_LOW = 4

    def get_level_buckets_by_ip(self, ip: str, days: int = 7) -> Dict[str, Any]:
        """按 IP + 时间窗做**服务端聚合**的精确分级计数。

        ⚠️ 必须用聚合，不能用「取 N 条文档再客户端分桶」——后者会严重失真：
        实测 192.168.0.30 在 7 天窗内有 4805 条告警（level>=4 共 1637 条，
        含 99 条 level-13 critical、635 条 level-10 high），但该 IP 同时有
        47 万条 level-3 噪音告警。按 @timestamp 倒序取最近 1000 条文档，
        几乎全是 level-3 噪音，critical/high 全被截断 → 客户端分桶得出
        「total 204，critical 0，high 0」。

        在安全工具里把 99 条 critical 报成 0，是会让人误判「这台机器很安全」的
        假阴性，比查询失败更危险。故此处只用 size=0 的 terms 聚合。

        返回 {critical, high, medium, low, total, window_days, exact}
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        body = {
            "size": 0,
            "query": {
                "bool": {
                    "filter": [
                        {"match": {"agent.ip": ip}},
                        {"range": {"@timestamp": {
                            "gte": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "lte": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        }}},
                    ]
                }
            },
            # size=32 足以覆盖 Wazuh level 0-15 的全部取值
            "aggs": {"by_level": {"terms": {"field": "rule.level", "size": 32}}},
        }
        result = self._os_search(body)
        buckets = {"critical": 0, "high": 0, "medium": 0, "low": 0, "total": 0}
        for b in result.get("aggregations", {}).get("by_level", {}).get("buckets", []):
            try:
                lvl = int(b["key"])
            except (TypeError, ValueError):
                continue
            cnt = b.get("doc_count", 0)
            if lvl >= self.LEVEL_CRITICAL:
                buckets["critical"] += cnt
            elif lvl >= self.LEVEL_HIGH:
                buckets["high"] += cnt
            elif lvl >= self.LEVEL_MEDIUM:
                buckets["medium"] += cnt
            elif lvl >= self.LEVEL_LOW:
                buckets["low"] += cnt
            # level<4 视为噪音，不计入（与 report_generator 口径一致）
        buckets["total"] = buckets["critical"] + buckets["high"] + buckets["medium"] + buckets["low"]
        buckets["window_days"] = days
        buckets["exact"] = True  # 聚合计数，无截断
        return buckets

    def get_high_severity_samples(self, ip: str, days: int = 7, limit: int = 5) -> List[Dict[str, Any]]:
        """取该 IP 近 days 天 level>=10 的高危告警样例（按时间倒序）。

        与计数分离：计数用聚合，样例才取文档。这样样例的 limit 截断
        不会影响计数准确性。
        """
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        body = {
            "size": limit,
            "query": {
                "bool": {
                    "filter": [
                        {"match": {"agent.ip": ip}},
                        {"range": {"rule.level": {"gte": self.LEVEL_HIGH}}},
                        {"range": {"@timestamp": {
                            "gte": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "lte": end.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        }}},
                    ]
                }
            },
            "sort": [{"@timestamp": {"order": "desc"}}],
        }
        result = self._os_search(body)
        out = []
        for h in result.get("hits", {}).get("hits", []):
            src = h.get("_source", {})
            rule = src.get("rule", {}) or {}
            out.append({
                "level": rule.get("level"),
                "description": (rule.get("description") or "")[:150],
                "timestamp": src.get("@timestamp"),
            })
        return out

    # ── 单条告警详情 ──────────────────────────────────

    def get_alert_by_id(self, alert_id: str) -> Dict[str, Any]:
        # 兼容两种 id：OpenSearch 内部 _id，以及 _source.id（Wazuh 逻辑 id，
        # 即 list/normalize 端点对外暴露的 id）。两者常不一致，故用 should 合并查询。
        body = {
            "query": {
                "bool": {
                    "should": [
                        {"term": {"id": alert_id}},
                        {"ids": {"values": [alert_id]}},
                    ],
                    "minimum_should_match": 1,
                }
            },
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
        agent_id: str = None,
    ) -> Dict[str, Any]:
        filters = []

        # 时间过滤
        if start_time or end_time:
            time_range = {}
            if start_time:
                time_range["gte"] = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            if end_time:
                time_range["lte"] = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            filters.append({"range": {"@timestamp": time_range}})

        # Agent ID 过滤
        if agent_id:
            filters.append({"term": {"agent.id": agent_id}})

        body = {
            "size": 0,
            "query": {"bool": {"filter": filters}} if filters else {"match_all": {}},
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

    # ── 告警指纹聚合（去重为"告警簇"）────────────────

    def _build_time_filter(
        self,
        hours: int = None,
        start_time: datetime = None,
        end_time: datetime = None,
    ) -> list:
        """构造 @timestamp 时间过滤（hours 或显式区间二选一）。"""
        filters = []
        if start_time or end_time:
            tr: dict = {}
            if start_time:
                tr["gte"] = start_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            if end_time:
                tr["lte"] = end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            filters.append({"range": {"@timestamp": tr}})
        elif hours:
            now = datetime.utcnow()
            start = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
            filters.append({"range": {"@timestamp": {"gte": start}}})
        return filters

    def _build_group_sub_aggs(self) -> dict:
        """每个告警簇桶内的子聚合（不含 data.srcip，单独尽力而为查询）。"""
        return {
            "level_stats": {"stats": {"field": "rule.level"}},
            "first_seen": {"min": {"field": "@timestamp"}},
            "last_seen": {"max": {"field": "@timestamp"}},
            "sample": {
                "top_hits": {
                    "size": 1,
                    "sort": [{"@timestamp": {"order": "desc"}}],
                    "_source": ["id", "rule", "agent", "location", "full_log", "data"],
                }
            },
        }

    def get_alert_groups(
        self,
        hours: int = 24,
        min_count: int = 1,
        level: int = None,
        limit: int = 20,
        max_pages: int = 20,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        """
        将原始告警按 (rule.id, agent.id) 分桶聚合成有限个"告警簇"。

        指纹(fingerprint) = "{rule_id}|{agent_id}"，可逆向解析，便于单簇查询。
        返回 {total_groups, groups:[...]}，groups 按 doc_count 降序取 TopN。
        OpenSearch composite 聚合天然支持百万级，不触发 1 万条上限。
        """
        must = []
        if level is not None:
            must.append({"range": {"rule.level": {"gte": level}}})
        filters = self._build_time_filter(hours=hours)
        query = {"bool": {"must": must or [{"match_all": {}}], "filter": filters}}

        # 分页拉取 composite 桶（确保 TopN 准确，不受桶默认排序影响）
        buckets: list = []
        after_key = None
        for _ in range(max(1, max_pages)):
            body = {
                "size": 0,
                "query": query,
                "aggs": {
                    "groups": {
                        "composite": {
                            "size": page_size,
                            "sources": [
                                {"rule_id": {"terms": {"field": "rule.id"}}},
                                {"agent_id": {"terms": {"field": "agent.id"}}},
                            ],
                            **({"after": after_key} if after_key else {}),
                        },
                        "aggs": self._build_group_sub_aggs(),
                    }
                },
            }
            result = self._os_search(body)
            agg = result.get("aggregations", {}).get("groups", {})
            buckets.extend(agg.get("buckets", []))
            after_key = agg.get("after_key")
            if not after_key:
                break

        normalized = []
        for b in buckets:
            key = b.get("key", {})
            rule_id = key.get("rule_id")
            agent_id = key.get("agent_id")
            ls = b.get("level_stats", {})
            sample_hit = (b.get("sample", {}).get("hits", {}).get("hits") or [{}])[0]
            src = sample_hit.get("_source", {})
            normalized.append({
                "fingerprint": f"{rule_id}|{agent_id}",
                "rule_id": rule_id,
                "rule_description": (src.get("rule") or {}).get("description"),
                "agent_id": agent_id,
                "agent_name": (src.get("agent") or {}).get("name"),
                "agent_ip": (src.get("agent") or {}).get("ip"),
                "count": b.get("doc_count", 0),
                "level_min": ls.get("min"),
                "level_max": ls.get("max"),
                "first_seen": (b.get("first_seen") or {}).get("value_as_string"),
                "last_seen": (b.get("last_seen") or {}).get("value_as_string"),
                "sample": self._normalize_alerts([sample_hit])[0]
                if (sample_hit and sample_hit.get("_source")) else None,
            })
        normalized = [g for g in normalized if g["count"] >= min_count]
        normalized.sort(key=lambda g: g["count"], reverse=True)
        return {"total_groups": len(normalized), "groups": normalized[:limit]}

    def get_alert_group_detail(
        self,
        fingerprint: str,
        hours: int = 24,
        sample_size: int = 5,
    ) -> Dict[str, Any]:
        """
        单簇明细：解析指纹 -> 查该簇全部样本 + 等级/时间聚合 + 关联资产。
        攻击者源 IP（data.srcip）为尽力而为：字段类型不确定时自动降级，不影响主结果。
        """
        if "|" not in fingerprint:
            raise ValueError("指纹格式应为 'rule_id|agent_id'")
        rule_id, agent_id = fingerprint.split("|", 1)
        filters = self._build_time_filter(hours=hours)
        filters.append({"term": {"rule.id": rule_id}})
        filters.append({"term": {"agent.id": agent_id}})
        body = {
            "size": 0,
            "query": {"bool": {"filter": filters}},
            "aggs": {
                "level_stats": {"stats": {"field": "rule.level"}},
                "first_seen": {"min": {"field": "@timestamp"}},
                "last_seen": {"max": {"field": "@timestamp"}},
                "samples": {
                    "top_hits": {
                        "size": sample_size,
                        "sort": [{"@timestamp": {"order": "desc"}}],
                        "_source": ["id", "rule", "agent", "location", "full_log", "data"],
                    }
                },
            },
        }
        result = self._os_search(body)
        aggs = result.get("aggregations", {})
        hits = aggs.get("samples", {}).get("hits", {}).get("hits", [])
        samples = self._normalize_alerts(hits) if hits else []
        agent_ip = (samples[0].get("agent") or {}).get("ip") if samples else None
        agent_name = (samples[0].get("agent") or {}).get("name") if samples else None
        rule_desc = (samples[0].get("rule") or {}).get("description") if samples else None
        total = aggs.get("samples", {}).get("hits", {}).get("total", {}).get("value", 0)

        # 攻击者源 IP：尽力而为，失败不影响主结果
        top_srcips, distinct_srcips = self._best_effort_srcip(filters)

        # IP -> 资产关联
        linked_asset = self._find_asset(agent_id=agent_id, agent_ip=agent_ip)

        return {
            "fingerprint": fingerprint,
            "rule_id": rule_id,
            "rule_description": rule_desc,
            "agent_id": agent_id,
            "agent_name": agent_name,
            "agent_ip": agent_ip,
            "count": total,
            "level_min": (aggs.get("level_stats") or {}).get("min"),
            "level_max": (aggs.get("level_stats") or {}).get("max"),
            "first_seen": (aggs.get("first_seen") or {}).get("value_as_string"),
            "last_seen": (aggs.get("last_seen") or {}).get("value_as_string"),
            "top_srcips": top_srcips,
            "distinct_srcips": distinct_srcips,
            "linked_asset": linked_asset,
            "samples": samples,
        }

    def _best_effort_srcip(self, filters: list) -> tuple:
        """尽力而为地聚合攻击者源 IP。data.srcip 字段类型依赖索引映射，
        先试 data.srcip，失败再试 .keyword，都失败则降级为空。"""
        candidates = [self._srcip_field_cached] if self._srcip_field_cached else [
            "data.srcip", "data.srcip.keyword",
        ]
        for field in candidates:
            if not field:
                continue
            try:
                body = {
                    "size": 0,
                    "query": {"bool": {"filter": filters}},
                    "aggs": {
                        "top_srcips": {"terms": {"field": field, "size": 10}},
                        "distinct_srcips": {"cardinality": {"field": field}},
                    },
                }
                res = self._os_search(body)
                aggs = res.get("aggregations", {})
                self._srcip_field_cached = field
                return (
                    [b["key"] for b in aggs.get("top_srcips", {}).get("buckets", [])],
                    aggs.get("distinct_srcips", {}).get("value", 0),
                )
            except Exception as e:
                logger.warning("srcip 聚合失败(field=%s): %s，尝试下一候选", field, e)
                continue
        return ([], 0)

    def _find_asset(self, agent_id: str = None, agent_ip: str = None) -> Optional[Dict[str, Any]]:
        """按 wazuh_agent_id 或 asset_ip 关联资产。"""
        if not agent_id and not agent_ip:
            return None
        from app.models import Asset
        q = self.db.query(Asset)
        if agent_id:
            q = q.filter(Asset.wazuh_agent_id == agent_id)
        else:
            q = q.filter(Asset.asset_ip == agent_ip)
        asset = q.first()
        if not asset:
            return None
        return {
            "asset_id": str(asset.id),
            "name": asset.name,
            "asset_ip": asset.asset_ip,
            "criticality": asset.criticality,
            "owner": asset.owner,
            "business_unit": asset.business_unit,
        }

    def close(self):
        self._os.close()
