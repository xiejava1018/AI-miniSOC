"""ATT&CK 技战术模型（OH-4.4 · S6）

表：
  soc_attack_patterns          技战术目录（离线种子自 configs/attack_patterns.yaml）
  soc_alert_attack_mappings    Wazuh 规则 → 技战术映射（rule_id 精确 / 组前缀）
"""
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base

# 映射方式
MATCH_RULE_ID = "rule_id"        # 精确规则 id（confidence 0.9）
MATCH_RULE_GROUPS = "rule_groups"  # Wazuh 规则组前缀（confidence 0.6）


class AttackPattern(Base):
    """一条 ATT&CK 技战术（含子技术）。"""

    __tablename__ = "soc_attack_patterns"

    technique_id = Column(String(20), primary_key=True)   # T1110 / T1110.001
    name = Column(String(200), nullable=False)
    tactic = Column(String(20), nullable=False)            # TA0006
    url = Column(String(500))

    updated_at = Column(
        DateTime(timezone=True), nullable=False,
        server_default=func.now(), onupdate=func.now(),
    )

    __table_args__ = (
        Index("idx_soc_attack_patterns_tactic", "tactic"),
    )

    def __repr__(self) -> str:
        return f"<AttackPattern {self.technique_id} {self.name}>"


class AlertAttackMapping(Base):
    """Wazuh 规则 → ATT&CK 技战术映射。"""

    __tablename__ = "soc_alert_attack_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=func.gen_random_uuid())

    technique_id = Column(
        String(20),
        ForeignKey("soc_attack_patterns.technique_id", ondelete="CASCADE"),
        nullable=False,
    )
    # 二选一：精确 rule_id（如 "5710"）或组前缀（如 "syscheck"）
    match_type = Column(String(20), nullable=False)
    match_value = Column(String(200), nullable=False)

    confidence = Column(Float, nullable=False, server_default="0.6")
    source = Column(String(20), nullable=False, server_default="seed")
    # seed=离线种子；manual=人工修订（sync 不覆盖）
    manual_override = Column(String(1), nullable=False, server_default="0")

    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())

    __table_args__ = (
        # 一个映射键（match_type+value+technique）唯一，防重复种子
        Index(
            "uq_soc_alert_attack_mapping",
            "match_type", "match_value", "technique_id",
            unique=True,
        ),
        Index("idx_soc_alert_attack_mapping_rule", "match_value"),
    )

    def __repr__(self) -> str:
        return (
            f"<AlertAttackMapping {self.match_type}={self.match_value} "
            f"→ {self.technique_id}>"
        )
