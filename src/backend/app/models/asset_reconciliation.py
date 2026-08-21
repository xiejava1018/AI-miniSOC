"""资产对账结果模型（P3 / F1.3）

台账（soc_assets）与实际网络（Wazuh Agent 列表）的差异记录。

三层数据健康的边界（PRD F1.3 明确要求，勿混淆）：
  soc_source_health      基础设施层：采集器/同步任务还在不在工作
  soc_sync_dead_letter   数据层：同步过程中被丢弃/失败的数据
  soc_asset_reconciliations  业务层（本表）：台账与实际网络的差异
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base

# 差异类型
TYPE_SHADOW = "shadow"      # 影子资产：Wazuh 有 Agent，台账没有
TYPE_OFFLINE = "offline"    # 疑似下线：台账有，Wazuh 侧已断开/Agent 不存在
TYPE_MISMATCH = "mismatch"  # 信息不一致：IP / 主机名 / OS 与台账不符

# 状态机：pending 为唯一可处理入口，三个终态互斥且不可逆
STATUS_PENDING = "pending"
STATUS_CONFIRMED = "confirmed"  # 确认差异属实（如确认是影子资产，但暂不补录）
STATUS_IGNORED = "ignored"      # 忽略（如已知的测试机，不必处理）
STATUS_RESOLVED = "resolved"    # 已处理（已补录台账 / 已标记下线 / 已修正信息）

TERMINAL_STATUSES = (STATUS_CONFIRMED, STATUS_IGNORED, STATUS_RESOLVED)


class AssetReconciliation(Base):
    """一条对账差异。一次对账（run_id 相同）通常产生多条。"""

    __tablename__ = "soc_asset_reconciliations"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())

    # 批次标识。PRD 的表结构里没有这一列，但"查询最近一次对账结果"必须能分批，
    # 否则历史差异会和本次混在一起。故新增（与 compliance 的 runs/findings 双表
    # 方案不同，这里用单表 + run_id，避免为一张结果表再引入一张 runs 表）。
    run_id = Column(UUID(as_uuid=True), nullable=False)

    # 关联的同步任务（PRD 要求：对账结果须能追溯到依据的同步任务）。
    # 对账主要实时读 Wazuh API，台账侧才来自同步，故此列可空。
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("soc_sync_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )

    # 影子资产在台账里本就不存在，故可空
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("soc_assets.id", ondelete="CASCADE"),
        nullable=True,
    )

    reconciliation_type = Column(String(20), nullable=False)

    # 差异详情 + 数据新鲜度快照。结构见 services/asset_reconciliation.py 的 _details_*
    details = Column(JSONB, nullable=False, server_default="{}")

    status = Column(String(20), nullable=False, server_default=STATUS_PENDING)

    # 处理人用户名快照（谁处理的）。审计细节另落 soc_audit_logs。
    resolved_by = Column(String(255))
    resolved_at = Column(DateTime(timezone=True))
    resolve_note = Column(Text)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        # 列表页主查询：按批次 + 状态过滤
        Index("idx_soc_asset_recon_run", "run_id", "status"),
        # "这台资产历史上有哪些差异"
        Index("idx_soc_asset_recon_asset", "asset_id"),
        # 待处理队列（数据健康页的红点计数）
        Index(
            "idx_soc_asset_recon_pending",
            "created_at",
            postgresql_where=Column("status") == STATUS_PENDING,
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<AssetReconciliation {self.reconciliation_type} "
            f"status={self.status} asset={self.asset_id}>"
        )
