"""行为画像模型（Behavior Profile）

docs/design/2026-09-05-用户IP行为画像-方案设计.md §9.2（v1.5）

三张表：
  - soc_behavior_profiles          行为画像日快照（每主体每日一行）
  - soc_behavior_domains           域名级日明细（突破 Loki 7 天留存，支撑 ≥180 天）
  - soc_behavior_profile_watermark 快照水位（断点补拉，§9.3）

主体键设计（v1.5 评审修订）：
  唯一键为 (asset_id, profile_date)；DHCP 场景 IP 漂移时按 asset_id 归并。
  asset_id 可空（未纳管设备），ip 侧仅建普通索引用于查询。
"""

from sqlalchemy import (
    BigInteger, Column, Date, DateTime, ForeignKey, Index, Integer,
    SmallInteger, String, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.models.base import Base


class BehaviorProfile(Base):
    """行为画像日快照（每主体每日一行）

    快照内容 = 该日当天的行为分布（by_hour/wd_hour/by_block 为单日口径，
    多日聚合在 service 层做）；tags/cat_share 基于截至该日的滚动 7 天聚合。
    status='gap' 表示该日数据已超出 Loki 窗口、永久缺失（假绿防护，§9.7.9）。
    """
    __tablename__ = "soc_behavior_profiles"
    __table_args__ = (
        UniqueConstraint("asset_id", "profile_date", name="uq_behavior_profile_asset_date"),
        Index("ix_behavior_profile_ip_date", "ip", "profile_date"),
        Index("ix_behavior_profile_date", "profile_date"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    asset_id = Column(
        UUID(as_uuid=False), ForeignKey("soc_assets.id", ondelete="SET NULL"), nullable=True,
        comment="画像主体（唯一键组成部分）；未纳管设备为 NULL",
    )
    ip = Column(String(45), nullable=False, comment="展示用当前 IP（漂移时由快照任务更新）")
    mac = Column(String(32), nullable=True, comment="辅助归并键（DHCP 场景）")
    hostname = Column(String(255), nullable=True, comment="辅助归并键")
    profile_date = Column(Date, nullable=False, comment="快照日")
    status = Column(String(8), nullable=False, default="ok", comment="ok / gap（数据缺失）")
    total = Column(Integer, nullable=False, default=0, comment="当日访问次数")
    by_hour = Column(JSONB, nullable=True, comment="24 小时分布 [0..23]")
    wd_hour = Column(JSONB, nullable=True, comment="7x24 星期x小时矩阵（当日行仅 weekday 行非零）")
    by_block = Column(JSONB, nullable=True, comment="7 时段分布")
    cat_share = Column(JSONB, nullable=True, comment="兴趣分类占比（滚动 7 天，仅 ACT 层）")
    cat_by_block = Column(JSONB, nullable=True, comment="分类x时段（当日 ACT 层计数）")
    workday = Column(Integer, nullable=False, default=0, comment="工作日访问次数")
    weekend = Column(Integer, nullable=False, default=0, comment="周末访问次数")
    layer_visit = Column(JSONB, nullable=True, comment="ACT/SYS/AD 三层占比")
    top_domains = Column(JSONB, nullable=True, comment="TOP 域名 [{domain,visits,category,share}]")
    tags = Column(JSONB, nullable=True, comment="画像标签 [{name,alias,desc,color,evidence}]")
    traffic_type = Column(String(8), nullable=False, default="human", comment="human/machine/mixed")
    confidence = Column(SmallInteger, nullable=False, default=0, comment="置信度 0-100")
    truncated_windows = Column(Integer, nullable=False, default=0, comment="被截断的查询窗口数")
    generated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class BehaviorDomain(Base):
    """域名级日明细（每主体每域名每日一行）

    解决 Loki 仅 7 天留存：聚合后落库留存 ≥180 天（§6 合规上限），
    支撑"域名 TOP N 下钻"与"长期新增域名速率"。
    """
    __tablename__ = "soc_behavior_domains"
    __table_args__ = (
        UniqueConstraint("asset_id", "domain", "profile_date", name="uq_behavior_domain_key"),
        Index("ix_behavior_domain_ip_date", "ip", "profile_date"),
        Index("ix_behavior_domain_date", "profile_date"),
    )

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    asset_id = Column(
        UUID(as_uuid=False), ForeignKey("soc_assets.id", ondelete="SET NULL"), nullable=True,
    )
    ip = Column(String(45), nullable=False)
    domain = Column(String(255), nullable=False)
    profile_date = Column(Date, nullable=False)
    visits = Column(Integer, nullable=False, default=0, comment="当日访问次数")
    category = Column(String(32), nullable=False, default="其他", comment="分类（与 classifier 一致）")


class BehaviorProfileWatermark(Base):
    """快照水位（单行表，id=1）

    snapshot_job 启动时对比 last_completed_date 与今天，补齐 ≤7 天内的缺口日；
    超出 Loki 窗口的缺日落 status='gap' 占位快照（§9.3 断点补拉）。
    """
    __tablename__ = "soc_behavior_profile_watermark"

    id = Column(SmallInteger, primary_key=True, default=1)
    last_completed_date = Column(Date, nullable=True, comment="最后成功完成的快照日")
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(),
                        onupdate=func.now())
