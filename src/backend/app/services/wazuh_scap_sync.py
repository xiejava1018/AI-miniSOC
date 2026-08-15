"""
Wazuh SCAP漏洞数据同步服务（DEPRECATED：真实数据源已由 opensearch_scap_sync.py 接管）

T5（2026-08-15）：POC-1 证实 Wazuh API 无 /vulnerability 路由，本服务的真实同步路径
已废弃（POST /sync/wazuh 已改指 OpenSearchSCAPSyncService）。保留原因：
- mock 分支（MockSCAPDataGenerator 同构落库）仍被 OpenSearchSCAPSyncService._sync_mock 复用；
- get_sync_status（纯 DB 统计）仍被 GET /sync/wazuh/status 使用；
- 保留代码便于回滚（设计 §6）。
不要新增对本服务真实同步路径的依赖。
"""

import logging
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.services.wazuh_client import wazuh_client
from app.models.vulnerability import Vulnerability, AssetVulnerability
from app.models.asset import Asset
from app.schemas.vulnerability import SeverityEnum, ScannerEnum, VulnerabilityStatusEnum
from sqlalchemy import func as sqlalchemy_func

logger = logging.getLogger(__name__)


class WazuhSCAPSyncService:
    """Wazuh SCAP漏洞数据同步服务"""

    # CVE严重程度映射
    SEVERITY_MAPPING = {
        "Critical": SeverityEnum.CRITICAL,
        "High": SeverityEnum.HIGH,
        "Medium": SeverityEnum.MEDIUM,
        "Low": SeverityEnum.LOW,
        "None": SeverityEnum.LOW
    }

    # 严重程度评分（用于CVSS计算）
    SEVERITY_TO_CVSS = {
        "Critical": 9.5,
        "High": 7.5,
        "Medium": 5.0,
        "Low": 2.5,
        "None": 0.0
    }

    @classmethod
    def sync_all_vulnerabilities(
        cls,
        db: Session,
        limit: int = 1000
    ) -> Dict[str, int]:
        """
        同步所有agent的SCAP漏洞数据

        Args:
            db: 数据库会话
            limit: 单次同步的最大数量

        Returns:
            同步结果统计
        """
        stats = {
            "total_agents": 0,
            "processed_agents": 0,
            "new_vulnerabilities": 0,
            "new_associations": 0,
            "updated_associations": 0,
            "errors": 0
        }

        try:
            # 获取所有agents
            agents = wazuh_client.get_agents()
            stats["total_agents"] = len(agents)

            for agent in agents:
                agent_id = agent.get("id")
                agent_name = agent.get("name")

                if not agent_id or agent.get("status") != "active":
                    continue

                try:
                    # 同步单个agent的漏洞
                    agent_stats = cls.sync_agent_vulnerabilities(
                        db=db,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        limit=limit
                    )

                    stats["processed_agents"] += 1
                    stats["new_vulnerabilities"] += agent_stats.get("new_vulnerabilities", 0)
                    stats["new_associations"] += agent_stats.get("new_associations", 0)
                    stats["updated_associations"] += agent_stats.get("updated_associations", 0)

                    logger.info(f"Synced vulnerabilities for agent {agent_name}: {agent_stats}")

                except Exception as e:
                    stats["errors"] += 1
                    logger.error(f"Failed to sync agent {agent_id}: {e}")
                    continue

            db.commit()
            logger.info(f"Vulnerability sync completed: {stats}")

        except Exception as e:
            logger.error(f"Failed to sync vulnerabilities: {e}")
            db.rollback()
            raise

        return stats

    @classmethod
    def sync_agent_vulnerabilities(
        cls,
        db: Session,
        agent_id: str,
        agent_name: str,
        limit: int = 500
    ) -> Dict[str, int]:
        """
        同步单个agent的SCAP漏洞数据

        Args:
            db: 数据库会话
            agent_id: Wazuh Agent ID
            agent_name: Agent名称
            limit: 同步数量限制

        Returns:
            同步结果统计
        """
        stats = {
            "new_vulnerabilities": 0,
            "new_associations": 0,
            "updated_associations": 0
        }

        try:
            # 查找或创建资产
            asset = cls._get_or_create_asset(db, agent_id, agent_name)
            if not asset:
                logger.warning(f"Asset not found for agent {agent_id}, skipping")
                return stats

            # 获取agent的漏洞数据
            vulnerabilities = wazuh_client.get_vulnerabilities(
                agent_id=agent_id,
                limit=limit
            )

            logger.info(f"Retrieved {len(vulnerabilities)} vulnerabilities for agent {agent_name}")

            # 处理每个漏洞
            for vuln_data in vulnerabilities:
                try:
                    # 转换并入库
                    result = cls._process_vulnerability(
                        db=db,
                        vuln_data=vuln_data,
                        asset=asset
                    )

                    if result == "new":
                        stats["new_vulnerabilities"] += 1
                        stats["new_associations"] += 1
                    elif result == "new_association":
                        stats["new_associations"] += 1
                    elif result == "updated":
                        stats["updated_associations"] += 1

                except Exception as e:
                    logger.error(f"Failed to process vulnerability: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to sync agent vulnerabilities: {e}")
            raise

        return stats

    @classmethod
    def _get_or_create_asset(
        cls,
        db: Session,
        wazuh_agent_id: str,
        agent_name: str
    ) -> Optional[Asset]:
        """
        根据Wazuh Agent ID查找或创建资产

        Args:
            db: 数据库会话
            wazuh_agent_id: Wazuh Agent ID
            agent_name: Agent名称

        Returns:
            资产对象
        """
        # 尝试通过wazuh_agent_id查找
        asset = db.query(Asset).filter(
            Asset.wazuh_agent_id == wazuh_agent_id
        ).first()

        if not asset:
            # 尝试通过名称查找
            asset = db.query(Asset).filter(
                Asset.name == agent_name
            ).first()

            if asset:
                # 更新wazuh_agent_id
                asset.wazuh_agent_id = wazuh_agent_id
                db.flush()

        return asset

    @classmethod
    def _process_vulnerability(
        cls,
        db: Session,
        vuln_data: Dict[str, Any],
        asset: Asset
    ) -> str:
        """
        处理单个漏洞数据

        Args:
            db: 数据库会话
            vuln_data: Wazuh漏洞数据
            asset: 关联的资产

        Returns:
            处理结果: new/new_association/updated/skipped
        """
        # 提取CVE ID
        cve_id = vuln_data.get("cve", "")
        if not cve_id:
            return "skipped"

        # 检查漏洞是否已存在
        vulnerability = db.query(Vulnerability).filter(
            Vulnerability.cve_id == cve_id
        ).first()

        # 如果不存在，创建新漏洞
        is_new_vuln = False
        if not vulnerability:
            vulnerability = cls._create_vulnerability_from_wazuh(vuln_data, db=db)
            db.add(vulnerability)
            db.flush()  # 获取生成的ID
            is_new_vuln = True

        # 检查资产-漏洞关联是否已存在
        association = db.query(AssetVulnerability).filter(
            AssetVulnerability.asset_id == asset.id,
            AssetVulnerability.vulnerability_id == vulnerability.id,
            AssetVulnerability.scanner == ScannerEnum.WAZUH
        ).first()

        if not association:
            # 创建新关联
            association = AssetVulnerability(
                asset_id=asset.id,
                vulnerability_id=vulnerability.id,
                scanner=ScannerEnum.WAZUH,
                status=VulnerabilityStatusEnum.OPEN,
                detected_at=datetime.utcnow()
            )
            db.add(association)
            db.flush()

            return "new" if is_new_vuln else "new_association"

        return "updated"

    @classmethod
    def _create_vulnerability_from_wazuh(
        cls,
        vuln_data: Dict[str, Any],
        db: Session = None
    ) -> Vulnerability:
        """
        从Wazuh漏洞数据创建Vulnerability对象

        Args:
            vuln_data: Wazuh漏洞数据（mock 生成器同构）
            db: 可选 DB 会话（传入时 _check_exploit 查 CISA KEV 表，T6）

        Returns:
            Vulnerability对象
        """
        cve_id = vuln_data.get("cve", "")
        title = vuln_data.get("title", "")
        severity = vuln_data.get("severity", "Medium")
        published = vuln_data.get("published", "")
        references = vuln_data.get("references", {})
        detection_time = vuln_data.get("detected_at", {})

        # 映射严重程度
        severity_enum = cls.SEVERITY_MAPPING.get(severity, SeverityEnum.MEDIUM)

        # 计算CVSS评分（基于严重程度）
        cvss_score = cls.SEVERITY_TO_CVSS.get(severity, 5.0)

        # 构建引用列表
        reference_list = []
        if isinstance(references, dict):
            for ref_type, ref_value in references.items():
                if ref_value:
                    reference_list.append(f"{ref_type}: {ref_value}")
        elif isinstance(references, list):
            reference_list = references

        # 构建受影响软件包信息
        package_name = vuln_data.get("package", {}).get("name")
        package_version = vuln_data.get("package", {}).get("version")
        affected_packages_dict = None
        if package_name:
            affected_packages_dict = {
                "name": package_name,
                "version": package_version
            }

        # 创建漏洞对象
        vulnerability = Vulnerability(
            cve_id=cve_id,
            title=title or f"{cve_id} - {severity} severity",
            description=vuln_data.get("description", ""),
            cvss_score=cvss_score,
            cvss_vector=vuln_data.get("cvss_vector"),
            severity=severity_enum,
            affected_packages=affected_packages_dict,
            fix_suggestion=vuln_data.get("fix", {}).get("version"),
            references=reference_list if reference_list else None,
            published_date=published if published else None,
            has_exploit=cls._check_exploit(cve_id, db=db),
            discovered_at=datetime.utcnow()
        )

        return vulnerability

    @classmethod
    def _check_exploit(cls, cve_id: str, db: Session = None) -> bool:
        """
        检查CVE是否有在野利用（T6 决策2：接入 CISA KEV）

        有 DB 会话时查本地 soc_cisa_kev 缓存表（由 cisa_kev_service 24h 同步）；
        无会话/查询失败时返回 False（保守）。配置弱点类无 CVE，不适用。
        """
        if db is None or not cve_id:
            return False
        try:
            from app.services.cisa_kev_service import CisaKevService
            return CisaKevService.is_known_exploit(db, cve_id)
        except Exception:
            return False

    @classmethod
    def get_sync_status(cls, db: Session) -> Dict[str, Any]:
        """
        获取同步状态

        Args:
            db: 数据库会话

        Returns:
            同步状态信息
        """
        # 统计数据库中的漏洞数量
        total_vulnerabilities = db.query(Vulnerability).count()
        total_associations = db.query(AssetVulnerability).filter(
            AssetVulnerability.scanner == ScannerEnum.WAZUH
        ).count()

        # 统计按严重程度分组
        severity_stats = db.query(
            Vulnerability.severity,
            sqlalchemy_func.count(Vulnerability.id)
        ).group_by(Vulnerability.severity).all()

        severity_distribution = {
            str(severity): count for severity, count in severity_stats
        }

        return {
            "total_vulnerabilities": total_vulnerabilities,
            "total_associations": total_associations,
            "severity_distribution": severity_distribution,
            "last_sync": None  # TODO: 从配置表获取最后同步时间
        }
