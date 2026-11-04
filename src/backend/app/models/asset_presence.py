"""资产存在性证据层模型（P1/P2/P3 资产失联治理）

第一性原理（见 2026-11-04 设计讨论）：
- 断言（台账 asset_status）与事实（观测）分离：传感器只报"我看到了 X"
- 缺席需要覆盖证明："扫过该网段但它不在结果里"才算失联证据
- 状态有时效：lifecycle_state 由观测+覆盖结算推导，任何观测可复活

三张承载：
  soc_assets 新列        last_seen_at / miss_streak / last_scan_missed_at / lifecycle_state
  soc_asset_observations 观测事实层（asset×source 心跳合并，防刷屏）
  soc_scan_coverage      扫描覆盖凭证（"我看过了"的证据，含失败凭证）
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from app.models.base import Base


class AssetObservation(Base):
    """观测事实层：某源在某时刻看到了某资产。

    按 (asset_id, source) 合并心跳（obs_count 累加），不逐条留痕——
    台账级体量下逐条观测表会无限膨胀，推导只需要"最后看到时间"。
    """

    __tablename__ = "soc_asset_observations"
    __table_args__ = (UniqueConstraint("asset_id", "source", name="uq_asset_observation_source"),)

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("soc_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 'scanner' / 'wazuh' / 'tplink-router' / ...（与 soc_asset_sources.source 同口径）
    source = Column(String(50), nullable=False)
    # 'active_scan' / 'sync' / 'manual'
    evidence_type = Column(String(20), nullable=False, default="sync")
    first_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    obs_count = Column(BigInteger, nullable=False, default=1)


class ScanCoverage(Base):
    """扫描覆盖凭证：一次扫描任务对每个目标的执行证据（含失败）。

    - status='success' 且 mode='internal'：结算缺席的依据
      （"覆盖声明 + 目标缺席" = 负证据，公理 2）
    - status='failed'：scheduled 连续失败告警的数据源
      （18 天瞎扫没人知道的事故，2026-10-17 ~ 11-04）
    - settled：该凭证是否已参与过缺席结算（幂等防重复计 miss）
    """

    __tablename__ = "soc_scan_coverage"
    __table_args__ = (
        UniqueConstraint("task_uuid", "target_value", name="uq_scan_coverage_task_target"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    task_uuid = Column(UUID(as_uuid=True), nullable=False, index=True)
    mode = Column(String(20), nullable=False)      # internal / public
    scope = Column(String(20))                     # manual / scheduled / auto
    target_value = Column(String(100), nullable=False)  # cidr 或 ip
    target_type = Column(String(10))               # cidr / ip
    status = Column(String(20), nullable=False)    # success / failed / cancelled
    hosts_found = Column(Integer)                  # 该目标发现的主机数（失败为 NULL）
    scanned_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    settled = Column(Boolean, nullable=False, default=False)
    settled_at = Column(DateTime(timezone=True))
    miss_marked = Column(Integer, nullable=False, default=0)  # 本次结算标记了几台失联
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
