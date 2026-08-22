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

# M3/T8：摘要卡 applications 计数服务实例（模块级单例，共享 5 分钟 _count 缓存）
_inventory_service = None


def _get_inventory_service():
    global _inventory_service
    if _inventory_service is None:
        from app.services.wazuh_inventory_service import WazuhInventoryService
        _inventory_service = WazuhInventoryService()
    return _inventory_service


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

        # 4. 端口数据（M4 双源：本地 AssetPort + Wazuh states 实时端口合并去重）
        open_ports, high_risk_ports, last_port_scan = self._get_port_stats(asset.id, asset.wazuh_agent_id)

        # 5. 标签数据
        tags = self._get_tags(asset.id)

        # 6. 漏洞/SCA 真实统计（M0 去伪：查 soc_asset_vulnerabilities JOIN soc_vulnerabilities）
        # - vuln_*: 仅 SCAP 类(CVE漏洞)，status=open
        # - sca_failed: SCA 类不合规项（同步语义只存 failed 项，pass_rate 本期不算见方案 §5）
        # - last_vuln_scan / last_sca_scan: 取关联表 max(detected_at)
        # - applications: M3 接入——OpenSearch states-inventory _count + 5分钟缓存，失败降级 0
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

        # M3/T8：应用计数（仅 Wazuh agent 资产；OpenSearch 失败降级 0，不阻塞摘要）
        applications = 0
        if asset.wazuh_agent_id:
            try:
                applications = _get_inventory_service().count_applications(asset.wazuh_agent_id)
            except Exception:
                logger.warning("applications 计数失败（OpenSearch 不可达），降级 0: %s", asset.asset_ip)

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

        高危阈值用全项目权威定义 LEVEL_HIGH=10（此前硬写 12，与报告/L2
        口径不一致）；且原实现对整数 level 存在 double-count bug
        （isinstance 判断加一次 + int() 转换又加一次，高危数翻倍）。
        失败兜底: 返回 (0, 0),不抛异常
        """
        if not wazuh_agent_id:
            return 0, 0

        try:
            alert_service = AlertQueryService(self.db)
            from datetime import timedelta
            from app.core.alert_levels import LEVEL_HIGH
            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(hours=24)

            stats = alert_service.get_alert_statistics(
                start_time=start_time,
                end_time=end_time,
                agent_id=wazuh_agent_id
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
                # OpenSearch terms 聚合的 key 可能是 int 或 str，统一转一次
                try:
                    if int(level) >= LEVEL_HIGH:
                        critical += count
                except (TypeError, ValueError):
                    continue
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

    def _get_port_stats(self, asset_id, wazuh_agent_id: Optional[str] = None) -> tuple[int, int, Optional[datetime]]:
        """
        端口统计（M4 双源合并去重，以 port+protocol 为键）:
        - open_ports: 开放端口总数（本地 state=open + Wazuh listening）
        - high_risk_ports: 命中高危端口库的端口数
        - last_port_scan: 最近一次扫描时间（本地表；Wazuh 实时无 scan_time 概念）
        - Wazuh 不可达时降级仅本地（与告警/应用清单同降级语义）
        """
        try:
            ports = (
                self.db.query(AssetPort)
                .filter(AssetPort.asset_id == asset_id, AssetPort.state == "open")
                .all()
            )
            port_keys = {f"{p.port}/{p.protocol}" for p in ports}
            open_count = len(ports)

            last_scan = max((p.scan_time for p in ports if p.scan_time), default=None)

            # M4：Wazuh states 实时监听端口合并（同 port+protocol 去重，避免双计）
            if wazuh_agent_id:
                try:
                    wazuh_ports = _get_inventory_service().get_ports(wazuh_agent_id)
                    for wp in wazuh_ports:
                        key = f"{wp.get('port')}/{wp.get('protocol')}"
                        if key not in port_keys:
                            port_keys.add(key)
                            open_count += 1
                except Exception as e:
                    logger.warning("Wazuh 实时端口获取失败，降级仅本地统计: %s", e)

            high_risk_count = sum(1 for key in port_keys if key.split("/")[0].isdigit() and int(key.split("/")[0]) in HIGH_RISK_PORTS)
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
