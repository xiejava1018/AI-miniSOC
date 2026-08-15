"""
资产安全摘要聚合服务

为资产详情页 v2 的"安全摘要"卡片提供聚合数据。
本服务对前端只读，Wazuh 缓存表相关字段在 Phase 2 接入后填充。
"""
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
import logging
import uuid

from app.models.asset import Asset
from app.models.asset_port import AssetPort
from app.models.asset_tag import AssetTag
from app.models.asset_incident import AssetIncident
from app.models.incident import Incident
from app.models.vulnerability import AssetVulnerability, Vulnerability
from app.services.alert_query import AlertQueryService

logger = logging.getLogger(__name__)


# 资产详情页 v2 引入:高危端口常量(与前端 src/frontend/src/constants/highRiskPorts.ts 保持一致)
# SOC 看端口表最关心"哪些是高危的、能不能关"
HIGH_RISK_PORTS = {
    22: {"risk": "high", "reason": "SSH 远程管理"},
    3389: {"risk": "high", "reason": "RDP 远程桌面"},
    23: {"risk": "high", "reason": "Telnet 明文协议"},
    445: {"risk": "high", "reason": "SMB 文件共享"},
    139: {"risk": "medium", "reason": "NetBIOS 文件共享"},
    21: {"risk": "medium", "reason": "FTP 明文传输"},
    3306: {"risk": "high", "reason": "MySQL 数据库"},
    1433: {"risk": "high", "reason": "SQL Server 数据库"},
    5432: {"risk": "high", "reason": "PostgreSQL 数据库"},
    27017: {"risk": "high", "reason": "MongoDB 数据库"},
    6379: {"risk": "high", "reason": "Redis 缓存"},
    2375: {"risk": "critical", "reason": "Docker 未授权 API"},
    9200: {"risk": "high", "reason": "Elasticsearch"},
    5601: {"risk": "high", "reason": "Kibana 控制台"},
}


def _map_status_to_online(asset_status: Optional[str]) -> str:
    """把 asset_status 字典值映射成统一的 online/offline/unknown"""
    if not asset_status:
        return "unknown"
    s = asset_status.lower()
    if s in ("online", "active", "connected"):
        return "online"
    if s in ("offline", "inactive", "disconnected", "decommissioned", "never_connected"):
        return "offline"
    return "unknown"


class AssetSummaryService:
    """
    资产安全摘要聚合服务

    设计原则:
    - 一次方法调用产出前端 6+ 个 MetricCard 所需全部指标
    - Wazuh 缓存表相关字段(应用/漏洞/SCA)在 Phase 2 接入后填充
    - 单资产维度,任何字段查询失败都降级返回兜底值,不抛异常
    """

    def __init__(self, db: Session):
        self.db = db

    def build_summary(self, asset_id: str) -> Dict[str, Any]:
        """
        构建资产安全摘要

        Returns:
            dict - 包含安全摘要所有指标,具体字段见 docs/design/2026-06-03-asset-detail-v2-design.md §7.1
        """
        try:
            asset_uuid = uuid.UUID(asset_id) if isinstance(asset_id, str) else asset_id
        except ValueError:
            logger.warning(f"无效的资产ID格式: {asset_id}")
            return self._empty_summary(asset_id)

        asset = self.db.query(Asset).filter(Asset.id == asset_uuid).first()
        if not asset:
            return self._empty_summary(asset_id)

        # 1. 在线状态
        online_status = _map_status_to_online(asset.asset_status)

        # 2. 告警数据(按 wazuh_agent_id 查询，失败降级为 0)
        alert_24h, alert_critical_24h = self._get_alert_stats(asset.wazuh_agent_id)

        # 3. 事件数据(本地 DB,JOIN asset_incidents)
        open_incidents = self._get_open_incidents_count(asset.id)

        # 4. 端口数据(本地 DB)
        open_ports, high_risk_ports, last_port_scan = self._get_port_stats(asset.id)

        # 5. 标签数据
        tags = self._get_tags(asset.id)

        # 6. 漏洞/SCA 真实统计（M0 去伪：查 soc_asset_vulnerabilities JOIN soc_vulnerabilities）
        # - vuln_*: 仅 SCAP 类(CVE漏洞)，status=open
        # - sca_failed: SCA 类不合规项（同步语义只存 failed 项，pass_rate 本期不算见方案 §5）
        # - last_vuln_scan / last_sca_scan: 取关联表 max(detected_at)
        # - applications: 保持 0（M3 应用清单接入后回填）
        applications = 0
        sca_pass_rate: Optional[float] = None
        sca_total = 0

        vuln_base = (
            self.db.query(AssetVulnerability)
            .join(Vulnerability, AssetVulnerability.vulnerability_id == Vulnerability.id)
            .filter(
                AssetVulnerability.asset_id == asset.id,
                AssetVulnerability.status == 'open',
            )
        )
        vuln_q = vuln_base.filter(Vulnerability.type == 'scap')
        vuln_total = vuln_q.count() or 0
        vuln_critical = vuln_q.filter(Vulnerability.severity == 'critical').count() or 0
        vuln_high = vuln_q.filter(Vulnerability.severity == 'high').count() or 0

        sca_q = vuln_base.filter(Vulnerability.type == 'sca')
        sca_failed = sca_q.count() or 0

        last_vuln_scan_dt = self.db.query(func.max(AssetVulnerability.detected_at)).filter(
            AssetVulnerability.asset_id == asset.id,
            AssetVulnerability.vulnerability_id.in_(
                self.db.query(Vulnerability.id).filter(Vulnerability.type == 'scap')
            )
        ).scalar()
        last_sca_scan_dt = self.db.query(func.max(AssetVulnerability.detected_at)).filter(
            AssetVulnerability.asset_id == asset.id,
            AssetVulnerability.vulnerability_id.in_(
                self.db.query(Vulnerability.id).filter(Vulnerability.type == 'sca')
            )
        ).scalar()
        last_vuln_scan = last_vuln_scan_dt.isoformat() if last_vuln_scan_dt else None
        last_sca_scan = last_sca_scan_dt.isoformat() if last_sca_scan_dt else None

        return {
            "asset_id": str(asset.id),
            "online_status": online_status,
            "alert_24h": alert_24h,
            "alert_critical_24h": alert_critical_24h,
            "open_incidents": open_incidents,
            "vuln_critical": vuln_critical,
            "vuln_high": vuln_high,
            "vuln_total": vuln_total,
            "open_ports": open_ports,
            "high_risk_ports": high_risk_ports,
            "applications": applications,
            "sca_pass_rate": sca_pass_rate,
            "sca_total": sca_total,
            "sca_failed": sca_failed,
            "last_port_scan": last_port_scan.isoformat() if last_port_scan else None,
            "last_vuln_scan": last_vuln_scan,
            "last_sca_scan": last_sca_scan,
            "data_classification": asset.data_classification or "internal",
            "owner": asset.owner,
            "owner_contact": asset.owner_contact,
            "tags": tags,
        }

    def _get_alert_stats(self, wazuh_agent_id: str) -> tuple[int, int]:
        """
        拉取近 24h 告警统计(总告警数 + 高危告警数)
        按 wazuh_agent_id 查询该资产的告警

        Wazuh 高危告警阈值: level >= 12
        失败兜底: 返回 (0, 0),不抛异常
        """
        # 没有 agent_id 则返回 0
        if not wazuh_agent_id:
            return 0, 0

        try:
            alert_service = AlertQueryService(self.db)
            from datetime import timedelta
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=24)

            # 按 agent_id 查询统计
            stats = alert_service.get_alert_statistics(
                start_time=start_time,
                end_time=end_time,
                agent_id=wazuh_agent_id  # 传入 agent_id 过滤
            )
            by_level = stats.get("by_level", [])

            total = 0
            critical = 0
            for bucket in by_level:
                level = bucket.get("key")
                count = bucket.get("doc_count", 0)
                if level is None:
                    continue
                total += count
                if isinstance(level, (int, float)) and level >= 12:
                    critical += count
                # OpenSearch 返回 level 可能是字符串
                try:
                    if int(level) >= 12:
                        critical += count
                except (TypeError, ValueError):
                    pass
            return total, critical
        except Exception as e:
            logger.warning(f"获取告警统计失败(agent_id={wazuh_agent_id}): {e}")
            return 0, 0

    def _get_open_incidents_count(self, asset_id) -> int:
        """
        统计该资产未关闭事件数(status != 'closed')
        """
        try:
            return (
                self.db.query(func.count(AssetIncident.asset_id))
                .join(Incident, AssetIncident.incident_id == Incident.id)
                .filter(
                    AssetIncident.asset_id == asset_id,
                    Incident.status.in_(["open", "in_progress", "resolved"])
                )
                .scalar()
            ) or 0
        except Exception as e:
            logger.warning(f"获取未关闭事件数失败(asset_id={asset_id}): {e}")
            return 0

    def _get_port_stats(self, asset_id) -> tuple[int, int, Optional[datetime]]:
        """
        端口统计:
        - open_ports: 开放端口总数(state='open')
        - high_risk_ports: 命中高危端口库的端口数
        - last_port_scan: 最近一次扫描时间
        """
        try:
            ports = (
                self.db.query(AssetPort)
                .filter(AssetPort.asset_id == asset_id, AssetPort.state == "open")
                .all()
            )
            open_count = len(ports)
            high_risk_count = sum(1 for p in ports if p.port in HIGH_RISK_PORTS)
            last_scan = max((p.scan_time for p in ports if p.scan_time), default=None)
            return open_count, high_risk_count, last_scan
        except Exception as e:
            logger.warning(f"获取端口统计失败(asset_id={asset_id}): {e}")
            return 0, 0, None

    def _get_tags(self, asset_id) -> List[Dict[str, str]]:
        """获取资产所有标签"""
        try:
            tags = (
                self.db.query(AssetTag)
                .filter(AssetTag.asset_id == asset_id)
                .all()
            )
            return [{"key": t.tag_key, "value": t.tag_value} for t in tags]
        except Exception as e:
            logger.warning(f"获取标签失败(asset_id={asset_id}): {e}")
            return []

    def _empty_summary(self, asset_id: str) -> Dict[str, Any]:
        """资产不存在时的兜底响应"""
        return {
            "asset_id": asset_id,
            "online_status": "unknown",
            "alert_24h": 0,
            "alert_critical_24h": 0,
            "open_incidents": 0,
            "vuln_critical": 0,
            "vuln_high": 0,
            "vuln_total": 0,
            "open_ports": 0,
            "high_risk_ports": 0,
            "applications": 0,
            "sca_pass_rate": None,
            "sca_total": 0,
            "sca_failed": 0,
            "last_port_scan": None,
            "last_vuln_scan": None,
            "last_sca_scan": None,
            "data_classification": "internal",
            "owner": None,
            "owner_contact": None,
            "tags": [],
        }
