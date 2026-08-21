"""
合规基线检查模型（PRD F3.3）

设计要点：
- soc_compliance_runs   : 一次巡检的汇总（含规则库版本，审计可复核）
- soc_compliance_findings: 仅落 fail / unknown 明细（可整改项）

【为何 pass 项不落明细】
判定是纯确定性函数（规则 + 当时字段值），pass 项数量占比大且无整改动作；
汇总表已记录逐规则 pass/fail/unknown 计数（审计所需的分子分母齐备），
单资产全量逐规则结果可由 `GET /compliance/assets/{id}` 即时重算得到。
这样 73 资产 × 16 规则的巡检只落几十行 finding，而非上千行冗余。
"""
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.models.base import Base


class ComplianceRun(Base):
    """合规巡检批次"""
    __tablename__ = "soc_compliance_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())

    ruleset_version = Column(String(20), nullable=False)   # 规则库版本（审计自证）
    ruleset_name = Column(String(100))
    rules_total = Column(Integer, nullable=False, default=0)

    assets_total = Column(Integer, nullable=False, default=0)     # 台账总数
    assets_in_scope = Column(Integer, nullable=False, default=0)  # 在网（判定范围内）

    pass_count = Column(Integer, nullable=False, default=0)
    fail_count = Column(Integer, nullable=False, default=0)
    unknown_count = Column(Integer, nullable=False, default=0)

    # 达标率 = pass/(pass+fail)，与覆盖率同时呈现；unknown 不计入分子分母
    compliance_rate = Column(Integer)     # 0-100 整数百分比，无可判定项时 NULL
    coverage_rate = Column(Integer)       # 可判定项 / 全部判定点

    stats = Column(JSONB)                 # 逐规则 / 逐严重度明细
    triggered_by = Column(String(100))    # 用户名 或 'scheduler'
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_soc_compliance_runs_created", created_at.desc()),
    )

    def __repr__(self) -> str:
        return (f"<ComplianceRun {self.id} v{self.ruleset_version} "
                f"pass={self.pass_count} fail={self.fail_count} unknown={self.unknown_count}>")


class ComplianceFinding(Base):
    """合规问题项（仅 fail / unknown）"""
    __tablename__ = "soc_compliance_findings"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    run_id = Column(UUID(as_uuid=True), ForeignKey("soc_compliance_runs.id", ondelete="CASCADE"),
                    nullable=False)
    asset_id = Column(UUID(as_uuid=True), ForeignKey("soc_assets.id", ondelete="CASCADE"),
                      nullable=False)

    rule_id = Column(String(32), nullable=False)        # 如 SOC-NET-001
    rule_version = Column(Integer, nullable=False)      # 规则自身版本
    rule_title = Column(String(200))
    category = Column(String(32))
    severity = Column(String(16))                       # critical/high/medium/low

    status = Column(String(16), nullable=False)         # fail / unknown
    reason = Column(Text)                               # 规则化判定依据（非 AI 生成）
    evidence = Column(JSONB)                            # 判定时读到的实际字段值

    # AI 解读层：仅对 fail 生成，unknown 不生成（缺数据该补数据，不该让 AI 猜）
    ai_remediation = Column(Text)
    ai_model = Column(String(50))
    ai_prompt_version = Column(String(40))
    ai_generated_at = Column(DateTime(timezone=True))

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("idx_soc_compliance_findings_run", "run_id", "status"),
        Index("idx_soc_compliance_findings_asset", "asset_id"),
        Index("idx_soc_compliance_findings_rule", "rule_id"),
    )

    def __repr__(self) -> str:
        return f"<ComplianceFinding {self.rule_id} {self.status} asset={self.asset_id}>"
