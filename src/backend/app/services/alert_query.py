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