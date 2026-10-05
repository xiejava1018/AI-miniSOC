"""整改工单模型（OH-4.6 · S10）

把两类「需要人处理的资产问题」统一成带责任链的整改工单：
  - reconciliation：对账差异（影子/掉线/信息不一致）
  - compliance：合规巡检 fail 项

责任链（字段即链）：created_by → assignee → resolved_by → verified_by。
S12 验证回路（OH-4.11）落地前 verified_* 不写——resolved 即终态；
落地后 verified 不通过可自动 reopen（status 回 open）。

与 soc_asset_reconciliations 的边界：
  对账表是「差异事实」，本表是「整改流程」。一条差异可派生一张工单
  （source 两列可回溯）；差异本身的状态机仍归对账服务管。
"""
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base

# 来源类型
SOURCE_RECONCILIATION = "reconciliation"
SOURCE_COMPLIANCE = "compliance"
VALID_SOURCES = (SOURCE_RECONCILIATION, SOURCE_COMPLIANCE)

# 状态机：open → in_progress → resolved（→ verified）
#   reopened：verified 不通过回 open（S12 预留）
#   cancelled：误报/不处理
STATUS_OPEN = "open"
STATUS_IN_PROGRESS = "in_progress"
STATUS_RESOLVED = "resolved"
STATUS_VERIFIED = "verified"
STATUS_REOPENED = "reopened"
STATUS_CANCELLED = "cancelled"

TERMINAL_STATUSES = (STATUS_VERIFIED, STATUS_CANCELLED)
VALID_STATUSES = (
    STATUS_OPEN, STATUS_IN_PROGRESS, STATUS_RESOLVED,
    STATUS_VERIFIED, STATUS_REOPENED, STATUS_CANCELLED,
)

# 状态迁移表（非法迁移在服务层拒绝）
ALLOWED_TRANSITIONS = {
    STATUS_OPEN: {STATUS_IN_PROGRESS, STATUS_CANCELLED},
    STATUS_IN_PROGRESS: {STATUS_RESOLVED, STATUS_CANCELLED},
    STATUS_RESOLVED: {STATUS_VERIFIED, STATUS_REOPENED, STATUS_CANCELLED},
    STATUS_REOPENED: {STATUS_IN_PROGRESS, STATUS_CANCELLED},
    STATUS_VERIFIED: set(),
    STATUS_CANCELLED: set(),
}

SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}


class RemediationTicket(Base):
    """一张整改工单。"""

    __tablename__ = "soc_remediation_tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())

    # 来源回溯（二选一；来源记录被删则置 NULL，工单保留）
    source_type = Column(String(32), nullable=False)
    reconciliation_id = Column(
        UUID(as_uuid=True),
        ForeignKey("soc_asset_reconciliations.id", ondelete="SET NULL"),
        nullable=True,
    )
    compliance_finding_id = Column(
        UUID(as_uuid=True),
        ForeignKey("soc_compliance_findings.id", ondelete="SET NULL"),
        nullable=True,

    )
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("soc_assets.id", ondelete="SET NULL"),
        nullable=True,
    )

    title = Column(String(200), nullable=False)
    severity = Column(String(16), nullable=False, server_default="medium")
    detail = Column(JSONB, nullable=False, server_default="{}")  # 来源摘要 + 建议快照

    status = Column(String(20), nullable=False, server_default=STATUS_OPEN)

    # 责任链
    created_by = Column(String(255), nullable=False)   # 派单人（或 system）
    assignee = Column(String(255))                     # 责任人用户名
    due_at = Column(DateTime(timezone=True))           # 整改期限
    resolved_by = Column(String(255))
    resolved_at = Column(DateTime(timezone=True))
    resolve_note = Column(Text)
    verified_by = Column(String(255))
    verified_at = Column(DateTime(timezone=True))

    occurrence_count = Column(Integer, nullable=False, server_default="1")
    last_activity_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        # 同一来源同时只允许一张未终态工单（防重复派单）。
        # PG 默认 NULL 互不相等，须用 NULLS NOT DISTINCT 的 partial unique index。
        Index(
            "uq_soc_remediation_recon_active",
            "reconciliation_id",
            unique=True,
            postgresql_where=text(
                "source_type = 'reconciliation' AND status NOT IN ('verified', 'cancelled')"
            ),
        ),
        Index(
            "uq_soc_remediation_comp_active",
            "compliance_finding_id",
            unique=True,
            postgresql_where=text(
                "source_type = 'compliance' AND status NOT IN ('verified', 'cancelled')"
            ),
        ),
        Index("idx_soc_remediation_status", "status", "created_at"),
        Index("idx_soc_remediation_asset", "asset_id"),
        Index("idx_soc_remediation_assignee", "assignee", "status"),
    )

    def __repr__(self) -> str:
        return f"<RemediationTicket {self.status} {self.source_type} {self.title}>"
