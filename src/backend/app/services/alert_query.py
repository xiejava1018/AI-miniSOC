"""
告警查询服务
使用 Wazuh API 查询告警数据
"""

from sqlalchemy.orm import Session
from app.core.config import settings
from app.services.wazuh_client import wazuh_client
import logging
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class AlertQueryService:
    """告警查询服务"""

    def __init__(self, db: Session):
        self.db = db

    def get_alerts(
        self,
        offset: int = 0,
        limit: int = 50,
        level: int = None,
        agent_id: str = None,
        start_time: datetime = None,
        end_time: datetime = None
    ) -> List[Dict[str, Any]]:
        """
        从 Wazuh API 查询告警
        注意: Wazuh 4.x 不直接提供告警列表 API
        返回模拟数据用于演示
        """
        # 返回模拟数据用于演示
        mock_alerts = [
            {
                "_id": "mock_alert_001",
                "@timestamp": "2026-03-19T09:00:00Z",
                "rule": {
                    "level": 5,
                    "description": "SSHD: Failed login attempt",
                    "id": 5710
                },
                "agent": {
                    "id": "002",
                    "name": "fnos-vm-ubuntu01",
                    "ip": "192.168.0.30"
                },
                "location": "192.168.0.30->/var/log/auth.log",
                "full_log": "Mar 19 09:00:00 fnos-vm-ubuntu01 sshd[12345]: Failed password for root from 192.168.0.100 port 22 ssh2"
            },
            {
                "_id": "mock_alert_002",
                "@timestamp": "2026-03-19T08:30:00Z",
                "rule": {
                    "level": 3,
                    "description": "SSHD: Attempt to login using a non-existent user",
                    "id": 5720
                },
                "agent": {
                    "id": "002",
                    "name": "fnos-vm-ubuntu01",
                    "ip": "192.168.0.30"
                },
                "location": "192.168.0.30->/var/log/auth.log",
                "full_log": "Mar 19 08:30:00 fnos-vm-ubuntu01 sshd[12346]: Invalid user admin from 192.168.0.100 port 22"
            }
        ]

        # 根据参数过滤
        filtered_alerts = mock_alerts
        if level is not None:
            filtered_alerts = [a for a in filtered_alerts if a["rule"]["level"] >= level]

        return filtered_alerts[offset:offset+limit]

    def get_alert_by_id(self, alert_id: str) -> Dict[str, Any]:
        """根据 ID 查询单个告警"""
        # 返回模拟数据
        return {
            "_id": alert_id,
            "@timestamp": "2026-03-19T09:00:00Z",
            "rule": {
                "level": 5,
                "description": "SSHD: Failed login attempt",
                "id": 5710,
                "groups": ["authentication_failed", "sshd"]
            },
            "agent": {
                "id": "002",
                "name": "fnos-vm-ubuntu01",
                "ip": "192.168.0.30"
            },
            "location": "192.168.0.30->/var/log/auth.log",
            "full_log": "Mar 19 09:00:00 fnos-vm-ubuntu01 sshd[12345]: Failed password for root from 192.168.0.100 port 22 ssh2",
            "geoip": {}
        }

    def get_alerts_by_ip(
        self,
        ip: str,
        offset: int = 0,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """根据 IP 查询告警"""
        # 返回模拟数据
        mock_alerts = [
            {
                "_id": f"alert_{ip}_001",
                "@timestamp": "2026-03-19T09:00:00Z",
                "rule": {
                    "level": 5,
                    "description": f"SSHD: Failed login attempt from {ip}",
                    "id": 5710
                },
                "agent": {
                    "id": "002",
                    "name": "fnos-vm-ubuntu01",
                    "ip": ip
                },
                "location": f"{ip}->/var/log/auth.log",
                "full_log": f"Failed password for root from {ip}"
            }
        ]

        return mock_alerts[offset:offset+limit]

    def get_alert_statistics(
        self,
        start_time: datetime = None,
        end_time: datetime = None
    ) -> Dict[str, Any]:
        """获取告警统计信息"""
        # 返回模拟统计数据
        return {
            "by_level": [
                {"key": "3", "doc_count": 15},
                {"key": "5", "doc_count": 8},
                {"key": "10", "doc_count": 3}
            ],
            "by_agent": [
                {"key": "fnos-vm-ubuntu01", "doc_count": 12},
                {"key": "pve-ubuntu01", "doc_count": 8},
                {"key": "xiejava-fnNAS", "doc_count": 5}
            ],
            "by_description": [
                {"key": "SSHD: Failed login attempt", "doc_count": 10},
                {"key": "SSHD: Attempt to login using a non-existent user", "doc_count": 6}
            ]
        }

    def get_alert_trend(
        self,
        hours: int = 24,
        interval_hours: int = 1
    ) -> List[Dict[str, Any]]:
        """
        获取近 N 小时告警趋势(按 interval_hours 桶聚合)

        真实实现:走 OpenSearch date_histogram
        mock 实现:返回 24 个伪数据点,数字按小时波动

        Returns:
            list of {"hour": ISO8601, "total": int, "critical": int}
        """
        from datetime import timedelta

        # 真实接入后改为 OpenSearch date_histogram 聚合
        # 这里 mock:按小时生成 24 个数据点(0-23 小时前)
        now = datetime.utcnow()
        # 模拟数据:总数在 [0, 15] 之间波动,高危在 [0, 3] 之间
        mock_buckets = [
            (3, 0), (5, 1), (8, 0), (12, 2), (15, 3), (10, 1),  # 0-5 时
            (6, 0), (4, 0), (7, 1), (11, 2), (9, 1), (13, 2),  # 6-11 时
            (14, 3), (10, 1), (8, 0), (5, 0), (7, 1), (9, 2),  # 12-17 时(工作时段)
            (11, 2), (6, 1), (4, 0), (3, 0), (5, 1), (7, 2),  # 18-23 时
        ]

        result = []
        for i in range(hours):
            bucket_time = now - timedelta(hours=(hours - 1 - i))
            total, critical = mock_buckets[i % len(mock_buckets)]
            result.append({
                "hour": bucket_time.isoformat() + "Z",
                "total": total,
                "critical": critical,
            })
        return result

    def get_top_alert_assets(
        self,
        hours: int = 24,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取近 N 小时告警最多的资产(IP 维度)

        真实实现:OpenSearch top by agent.ip,带 critical 计数
        mock 实现:返回硬编码的 IP 列表

        Returns:
            list of {"ip", "alert_count", "critical_count", "last_alert_at"}
        """
        from datetime import timedelta

        now = datetime.utcnow()
        mock_top = [
            {"ip": "192.168.0.2", "alert_count": 312, "critical_count": 8,
             "last_alert_at": (now - timedelta(minutes=3)).isoformat() + "Z"},
            {"ip": "192.168.0.30", "alert_count": 145, "critical_count": 3,
             "last_alert_at": (now - timedelta(minutes=12)).isoformat() + "Z"},
            {"ip": "192.168.0.35", "alert_count": 87, "critical_count": 1,
             "last_alert_at": (now - timedelta(hours=1)).isoformat() + "Z"},
            {"ip": "192.168.0.42", "alert_count": 56, "critical_count": 0,
             "last_alert_at": (now - timedelta(hours=2)).isoformat() + "Z"},
            {"ip": "192.168.0.50", "alert_count": 23, "critical_count": 0,
             "last_alert_at": (now - timedelta(hours=3)).isoformat() + "Z"},
        ]
        return mock_top[:limit]