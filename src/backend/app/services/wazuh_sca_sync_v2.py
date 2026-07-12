"""
Wazuh SCA (Security Configuration Assessment) 数据同步服务 v2
使用新的 SCA 专用表结构
"""

import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime

from app.services.wazuh_client import wazuh_client
from app.models.sca import ScaCheck, AssetScaCheck
from app.models.asset import Asset

logger = logging.getLogger(__name__)


class WazuhSCASyncServiceV2:
    """Wazuh SCA数据同步服务 v2 - 使用专用SCA表"""

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
            "new_checks": 0,
            "new_results": 0,
            "updated_results": 0,
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
                    stats["new_checks"] += agent_stats["new_checks"]
                    stats["new_results"] += agent_stats["new_results"]
                    stats["updated_results"] += agent_stats["updated_results"]

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
            "new_checks": 0,
            "new_results": 0,
            "updated_results": 0
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
                    # 同步该策略的检查结果
                    checks_stats = cls.sync_policy_checks(
                        db=db,
                        asset=asset,
                        agent_id=agent_id,
                        policy_id=policy_id,
                        policy_name=policy_name,
                        policy_data=policy
                    )

                    stats["new_checks"] += checks_stats["new_checks"]
                    stats["new_results"] += checks_stats["new_results"]
                    stats["updated_results"] += checks_stats["updated_results"]

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
            "new_checks": 0,
            "new_results": 0,
            "updated_results": 0
        }

        try:
            # 获取检查结果
            checks_data = wazuh_client._request(
                "GET",
                f"/sca/{agent_id}/checks/{policy_id}",
                params={"limit": 1000}
            )

            checks = checks_data.get("data", {}).get("affected_items", [])

            # 处理所有检查项（不只是failed）
            for check in checks:
                try:
                    check_id = check.get("id")

                    if not check_id:
                        continue

                    # 获取或创建检查项定义
                    sca_check = db.query(ScaCheck).filter(
                        ScaCheck.check_id == check_id,
                        ScaCheck.policy_id == policy_id
                    ).first()

                    if not sca_check:
                        # 创建新的检查项定义
                        sca_check = cls._create_sca_check(
                            check_id=check_id,
                            policy_id=policy_id,
                            policy_name=policy_name,
                            check=check
                        )

                        db.add(sca_check)
                        db.flush()  # 获取ID
                        stats["new_checks"] += 1

                    # 获取或创建资产检查结果
                    asset_check = db.query(AssetScaCheck).filter(
                        AssetScaCheck.asset_id == asset.id,
                        AssetScaCheck.sca_check_id == sca_check.id
                    ).first()

                    check_result = check.get("result", "not applicable")
                    scan_time = policy_data.get("end_scan") or datetime.utcnow()

                    if not asset_check:
                        # 创建新的资产检查结果
                        asset_check = AssetScaCheck(
                            asset_id=asset.id,
                            sca_check_id=sca_check.id,
                            result=check_result,
                            reason=check.get("reason", ""),
                            status="open",  # SCA检查默认为open状态
                            last_scan_time=scan_time
                        )

                        db.add(asset_check)
                        stats["new_results"] += 1

                    else:
                        # 更新现有检查结果
                        asset_check.result = check_result
                        asset_check.reason = check.get("reason", "")
                        asset_check.last_scan_time = scan_time
                        asset_check.updated_at = datetime.utcnow()
                        stats["updated_results"] += 1

                except Exception as e:
                    logger.error(f"处理SCA检查 {check.get('id')} 失败: {e}")

            db.commit()

        except Exception as e:
            logger.error(f"同步策略 {policy_id} 失败: {e}")
            db.rollback()
            raise

        return stats

    @classmethod
    def _create_sca_check(
        cls,
        check_id: int,
        policy_id: str,
        policy_name: str,
        check: Dict[str, Any]
    ) -> ScaCheck:
        """创建SCA检查项定义"""

        return ScaCheck(
            check_id=check_id,
            policy_id=policy_id,
            title=check.get("title", "配置检查项"),
            description=check.get("description", ""),
            rationale=check.get("rationale", ""),
            remediation=check.get("remediation", ""),
            compliance=check.get("compliance", []),
            rules=check.get("rules", []),
            condition=check.get("condition"),
            command=check.get("command"),
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )

    @classmethod
    def get_sca_statistics(cls, db: Session) -> Dict[str, Any]:
        """
        获取SCA检查统计数据

        Args:
            db: 数据库会话

        Returns:
            统计数据
        """
        from sqlalchemy import func

        # 总检查项数（去重）
        total_checks = db.query(func.count(ScaCheck.id)).scalar()

        # 总检查结果数
        total_results = db.query(func.count(AssetScaCheck.id)).scalar()

        # 按结果统计
        result_stats = db.query(
            AssetScaCheck.result,
            func.count(AssetScaCheck.id)
        ).group_by(AssetScaCheck.result).all()

        result_counts = {result: count for result, count in result_stats}

        # 按资产统计
        asset_stats = db.query(
            Asset.name,
            func.count(AssetScaCheck.id)
        ).join(
            AssetScaCheck, Asset.id == AssetScaCheck.asset_id
        ).group_by(Asset.name).all()

        asset_counts = {name: count for name, count in asset_stats}

        return {
            "total_checks": total_checks,
            "total_results": total_results,
            "by_result": result_counts,
            "by_asset": asset_counts
        }
