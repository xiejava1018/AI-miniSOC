"""
Wazuh SCA (Security Configuration Assessment) 数据同步服务
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


class WazuhSCASyncService:
    """Wazuh SCA数据同步服务"""

    # 映射严重程度（基于result）
    SEVERITY_MAPPING = {
        "failed": SeverityEnum.HIGH,  # 配置失败
        "passed": SeverityEnum.LOW,    # 配置通过
        "not applicable": SeverityEnum.LOW
    }

    # 映射严重程度到CVSS评分
    SEVERITY_TO_CVSS = {
        "failed": 7.0,     # 配置失败给7分
        "passed": 1.0,     # 配置通过给1分
        "not applicable": 0.0
    }

    @classmethod
    def sync_all_sca_checks(
        cls,
        db: Session,
        limit: int = 1000
    ) -> Dict[str, int]:
        """
        同步所有agent的SCA检查数据

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
                agent_ip = agent.get("ip")

                if not agent_id or agent.get("status") != "active":
                    continue

                try:
                    # 同步单个agent的SCA检查
                    agent_stats = cls.sync_agent_sca_checks(
                        db=db,
                        agent_id=agent_id,
                        agent_name=agent_name,
                        agent_ip=agent_ip,
                        limit=limit
                    )

                    stats["processed_agents"] += 1
                    stats["new_vulnerabilities"] += agent_stats["new_vulnerabilities"]
                    stats["new_associations"] += agent_stats["new_associations"]
                    stats["updated_associations"] += agent_stats["updated_associations"]

                except Exception as e:
                    logger.error(f"同步Agent {agent_id}的SCA数据失败: {e}")
                    stats["errors"] += 1

        except Exception as e:
            logger.error(f"SCA同步失败: {e}")
            raise

        return stats

    @classmethod
    def sync_agent_sca_checks(
        cls,
        db: Session,
        agent_id: str,
        agent_name: str,
        agent_ip: str,
        limit: int = 1000
    ) -> Dict[str, int]:
        """
        同步单个agent的SCA检查数据

        Args:
            db: 数据库会话
            agent_id: Agent ID
            agent_name: Agent名称
            agent_ip: Agent IP
            limit: 限制数量

        Returns:
            同步结果统计
        """
        stats = {
            "new_vulnerabilities": 0,
            "new_associations": 0,
            "updated_associations": 0
        }

        try:
            # 获取或创建资产
            asset = db.query(Asset).filter(
                Asset.wazuh_agent_id == agent_id
            ).first()

            if not asset:
                logger.warning(f"Agent {agent_id}对应的资产不存在，跳过SCA同步")
                return stats

            # 获取SCA策略列表
            policies_data = wazuh_client._request(
                "GET",
                f"/sca/{agent_id}",
                params={"limit": 100}
            )

            policies = policies_data.get("data", {}).get("affected_items", [])

            for policy in policies:
                policy_id = policy.get("policy_id")
                policy_name = policy.get("name")

                if not policy_id:
                    continue

                try:
                    # 获取该策略的详细检查结果
                    checks_stats = cls.sync_policy_checks(
                        db=db,
                        asset=asset,
                        agent_id=agent_id,
                        policy_id=policy_id,
                        policy_name=policy_name,
                        policy_data=policy
                    )

                    stats["new_vulnerabilities"] += checks_stats["new_vulnerabilities"]
                    stats["new_associations"] += checks_stats["new_associations"]
                    stats["updated_associations"] += checks_stats["updated_associations"]

                except Exception as e:
                    logger.error(f"同步策略 {policy_id} 失败: {e}")

        except Exception as e:
            logger.error(f"同步Agent {agent_id}的SCA检查失败: {e}")
            raise

        return stats

    @classmethod
    def sync_policy_checks(
        cls,
        db: Session,
        asset: Asset,
        agent_id: str,
        policy_id: str,
        policy_name: str,
        policy_data: Dict[str, Any]
    ) -> Dict[str, int]:
        """
        同步单个策略的SCA检查结果

        Args:
            db: 数据库会话
            asset: 资产对象
            agent_id: Agent ID
            policy_id: 策略ID
            policy_name: 策略名称
            policy_data: 策略数据

        Returns:
            同步结果统计
        """
        stats = {
            "new_vulnerabilities": 0,
            "new_associations": 0,
            "updated_associations": 0
        }

        try:
            # 获取检查结果
            # 正确的端点：/sca/{agent_id}/checks/{policy_id}
            checks_data = wazuh_client._request(
                "GET",
                f"/sca/{agent_id}/checks/{policy_id}",
                params={"limit": 1000}
            )

            checks = checks_data.get("data", {}).get("affected_items", [])

            # 只处理失败的检查项（result字段）
            failed_checks = [c for c in checks if c.get("result") == "failed"]

            for check in failed_checks:
                try:
                    # 创建唯一的SCA ID
                    sca_id = f"SCA-{policy_id}-{check.get('id')}"

                    # 检查是否已存在
                    existing = db.query(Vulnerability).filter(
                        Vulnerability.cve_id == sca_id
                    ).first()

                    if not existing:
                        # 创建新的脆弱性记录
                        vulnerability = cls._create_sca_vulnerability(
                            sca_id=sca_id,
                            policy_id=policy_id,
                            policy_name=policy_name,
                            check=check,
                            policy_data=policy_data
                        )

                        db.add(vulnerability)
                        db.flush()  # 获取ID

                        stats["new_vulnerabilities"] += 1

                        # 创建资产-漏洞关联
                        association = AssetVulnerability(
                            asset_id=asset.id,
                            vulnerability_id=vulnerability.id,
                            status=VulnerabilityStatusEnum.OPEN,
                            detected_at=policy_data.get("start_scan"),
                            # T7（评审修订）：scanner 必须用枚举值 wazuh_sca，
                            # 字面量 'wazuh-sca' 不在 ScannerEnum 内，会导致
                            # GET /asset-vulnerabilities 的 response_model 校验 500
                            scanner=ScannerEnum.WAZUH_SCA,
                            # T11：按严重度设修复时限（Phase 4.2 SLA）
                            due_date=AssetVulnerability.compute_due_date(
                                vulnerability.severity, policy_data.get("start_scan")
                            ),
                        )

                        db.add(association)
                        stats["new_associations"] += 1

                    else:
                        # 更新现有记录的时间戳
                        existing.updated_at = datetime.utcnow()

                        # 检查关联是否存在
                        existing_assoc = db.query(AssetVulnerability).filter(
                            AssetVulnerability.asset_id == asset.id,
                            AssetVulnerability.vulnerability_id == existing.id
                        ).first()

                        if existing_assoc:
                            existing_assoc.updated_at = datetime.utcnow()
                            stats["updated_associations"] += 1

                except Exception as e:
                    logger.error(f"处理SCA检查 {check.get('id')} 失败: {e}")

            db.commit()

        except Exception as e:
            logger.error(f"同步策略 {policy_id} 失败: {e}")
            db.rollback()
            raise

        return stats

    @classmethod
    def _create_sca_vulnerability(
        cls,
        sca_id: str,
        policy_id: str,
        policy_name: str,
        check: Dict[str, Any],
        policy_data: Dict[str, Any]
    ) -> Vulnerability:
        """创建SCA类型的脆弱性记录"""

        # 映射严重程度（基于result字段）
        check_result = check.get("result", "not applicable")
        severity = cls.SEVERITY_MAPPING.get(check_result, SeverityEnum.LOW)
        cvss_score = cls.SEVERITY_TO_CVSS.get(check_result, 3.0)

        # 生成CVSS向量（基于SCA规则）
        cvss_vector = f"AV:N/AC:L/PR:N/UI:N/S:U/C:{cls._get_cvss_c(check_result)}/I:{cls._get_cvss_i(check_result)}/A:{cls._get_cvss_a(check_result)}"

        return Vulnerability(
            cve_id=sca_id,
            type="sca",  # SCA类型
            title=check.get("title", "配置检查项"),
            description=check.get("description", ""),
            severity=severity,
            cvss_score=cvss_score,
            cvss_vector=cvss_vector,
            affected_packages=None,  # SCA无软件包
            fix_suggestion=check.get("remediation", ""),
            # SCA references存储为描述性文本，不使用结构化数据
            references=[f"Policy: {policy_name} ({policy_id})",
                       f"Benchmark: {policy_data.get('references', 'N/A')}"] if policy_data.get("references") else None,
            published_date=None,  # SCA无发布日期
            has_exploit=False,  # 配置弱点无exploit
            discovered_at=policy_data.get("start_scan"),
            updated_at=datetime.utcnow()
        )

    @staticmethod
    def _get_cvss_c(result: str) -> str:
        """根据result映射C值"""
        if result == "failed":
            return "H"
        elif result == "passed":
            return "L"
        else:
            return "N"

    @staticmethod
    def _get_cvss_i(result: str) -> str:
        """根据result映射I值"""
        if result == "failed":
            return "H"
        elif result == "passed":
            return "L"
        else:
            return "N"

    @staticmethod
    def _get_cvss_a(result: str) -> str:
        """根据result映射A值"""
        if result == "failed":
            return "H"
        elif result == "passed":
            return "L"
        else:
            return "N"
