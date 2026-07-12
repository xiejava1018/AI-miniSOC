"""
安全配置评估（SCA）模型
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, UniqueConstraint, Integer, Boolean
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class ScaCheck(Base):
    """SCA检查项定义表 - 存储检查项的元数据"""
    __tablename__ = "soc_sca_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    check_id = Column(Integer, nullable=False, index=True)  # Wazuh检查项ID，如33000
    policy_id = Column(String(100), nullable=False, index=True)  # 策略ID，如cis_debian12
    title = Column(String(500), nullable=False)  # 检查项标题
    description = Column(Text)  # 检查项描述
    rationale = Column(Text)  # 检查原因
    remediation = Column(Text)  # 修复建议
    compliance = Column(JSONB)  # 合规性标准，如CIS、PCI DSS
    rules = Column(JSONB)  # 检查规则
    condition = Column(String(20))  # 检查条件：all/any
    command = Column(String(500))  # 检查命令
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # 唯一约束：同一策略下的检查项ID唯一
    __table_args__ = (
        UniqueConstraint('check_id', 'policy_id', name='uq_sca_check_policy'),
    )

    # 关系
    asset_checks = relationship("AssetScaCheck", back_populates="sca_check", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ScaCheck(check_id={self.check_id}, policy_id={self.policy_id}, title={self.title})>"


class AssetScaCheck(Base):
    """资产SCA检查结果表 - 存储每个资产的检查结果"""
    __tablename__ = "soc_asset_sca_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    asset_id = Column(UUID(as_uuid=True), ForeignKey("soc_assets.id", ondelete="CASCADE"), nullable=False, index=True)
    sca_check_id = Column(UUID(as_uuid=True), ForeignKey("soc_sca_checks.id", ondelete="CASCADE"), nullable=False, index=True)
    result = Column(String(20), nullable=False)  # passed, failed, not applicable
    reason = Column(Text)  # 失败原因
    status = Column(String(20), nullable=False, default="open")  # open, in_progress, fixed
    last_scan_time = Column(DateTime(timezone=True), nullable=False)  # 最后扫描时间
    scan_score = Column(Integer)  # 合规得分（如果有）
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    # 唯一约束：同一资产在同一检查项上只有一条记录
    __table_args__ = (
        UniqueConstraint('asset_id', 'sca_check_id', name='uq_asset_sca_check'),
    )

    # 关系
    sca_check = relationship("ScaCheck", back_populates="asset_checks")

    def __repr__(self):
        return f"<AssetScaCheck(asset_id={self.asset_id}, sca_check_id={self.sca_check_id}, result={self.result})>"
