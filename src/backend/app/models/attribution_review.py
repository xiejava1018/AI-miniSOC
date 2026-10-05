"""资产归属确认模型（OH-UI.3 确认工作台）

来源：身份融合（identity_fusion.score_fusion）在资产同步路径上判定为
needs_review 的观测——它与某个已存在资产「像是同一实体但存在冲突信号」，
保守不自动新建/合并，转人工裁决。

与 soc_asset_reconciliations 的边界（勿混淆）：
  soc_asset_reconciliations  台账 vs 实际网络（Wazuh Agent 列表）的差异
                             （shadow / offline / mismatch）
  soc_attribution_reviews    一条待入库观测与候选资产之间的「身份归属冲突」
                             （identity_conflict）

状态机：pending 是唯一可处理入口；merged / created / dismissed 三终态
互斥且不可逆。终态后 observation_fingerprint 的唯一 partial 约束释放，
同一观测再次冲突时可产生新的 pending。
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
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base

# review_kind：v0.1 仅一种，为未来非融合类归属问题预留枚举
KIND_IDENTITY_CONFLICT = "identity_conflict"

STATUS_PENDING = "pending"
STATUS_MERGED = "merged"      # 已合并到（某一）候选资产
STATUS_CREATED = "created"    # 确认是不同实体，已新建资产
STATUS_DISMISSED = "dismissed"  # 忽略，不做动作

TERMINAL_STATUSES = (STATUS_MERGED, STATUS_CREATED, STATUS_DISMISSED)

# 裁决动作（POST .../resolve 的 decision 取值）
DECISION_MERGE = "merge"
DECISION_CREATE = "create"
DECISION_DISMISS = "dismiss"

VALID_DECISIONS = (DECISION_MERGE, DECISION_CREATE, DECISION_DISMISS)


class AttributionReview(Base):
    """一条身份归属待复核记录。"""

    __tablename__ = "soc_attribution_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())

    status = Column(String(20), nullable=False, server_default=STATUS_PENDING)
    review_kind = Column(String(20), nullable=False, server_default=KIND_IDENTITY_CONFLICT)

    # 触发复核的原始观测（仅白名单字段，见 attribution_service.OBSERVATION_FIELDS）
    observation = Column(JSONB, nullable=False)
    observation_fingerprint = Column(String(64), nullable=False)

    source = Column(String(50), nullable=False)
    sync_task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("soc_sync_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )

    # 裁决后关联的资产（merged：目标候选；created：新资产；dismissed：NULL）
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("soc_assets.id", ondelete="SET NULL"),
        nullable=True,
    )
    # pending 阶段评分最高的候选资产
    candidate_asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("soc_assets.id", ondelete="SET NULL"),
        nullable=True,
    )

    # 最佳候选 FusionResult.to_dict()
    best_score = Column(JSONB, nullable=False)
    # 全部候选 [{asset_id, asset_ip, name, score: FusionResult.to_dict()}]
    candidates = Column(JSONB, nullable=False, server_default="[]")
    candidate_count = Column(Integer, nullable=False, server_default="1")

    # 同一指纹重复触发计数（pending 期间只 bump 不新增）
    occurrence_count = Column(Integer, nullable=False, server_default="1")
    last_occurred_at = Column(DateTime(timezone=True), nullable=False)

    resolved_by = Column(String(255))
    resolved_at = Column(DateTime(timezone=True))
    resolve_note = Column(Text)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (
        # pending 队列去重硬保证：同指纹同时只允许一条 pending
        Index(
            "idx_soc_attr_review_fp_pending",
            "observation_fingerprint",
            unique=True,
            postgresql_where=Column("status") == STATUS_PENDING,
        ),
        # 工作台列表主查询
        Index("idx_soc_attr_review_status", "status", "created_at"),
        Index("idx_soc_attr_review_candidate", "candidate_asset_id"),
        Index("idx_soc_attr_review_asset", "asset_id"),
    )

    def __repr__(self) -> str:
        return (
            f"<AttributionReview {self.status} kind={self.review_kind} "
            f"candidate={self.candidate_asset_id}>"
        )
