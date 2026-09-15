"""
资产模型
"""

from sqlalchemy import Column, String, Text, DateTime, Date, Integer, ForeignKey, UniqueConstraint, Index, text
from sqlalchemy.dialects.postgresql import UUID, MACADDR, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.models.base import Base


class Asset(Base):
    """资产表"""
    __tablename__ = "soc_assets"
    __table_args__ = (
        UniqueConstraint('network_segment', 'asset_ip', name='uq_network_segment_ip'),
        # T0a：wazuh_agent_id 唯一部分索引（NULL 不受约束），防 agent 双挂串数据
        Index('uq_soc_assets_agent_id', 'wazuh_agent_id', unique=True,
              postgresql_where='wazuh_agent_id IS NOT NULL'),
        # 下面两个索引由迁移用原生 SQL 建（a7f8e9d0c1b2 / c2d3e4f5a6b7）。
        # 必须在 model 侧同步声明，否则 alembic autogenerate 认为库里多了索引而生成 DROP。
        # 列表页按风险倒序排序用（NULLS LAST：未评分资产排最后）
        Index('idx_soc_assets_risk_score', text('risk_score DESC NULLS LAST')),
        # EOL 到期预警扫描用，只索引已知 EOL 的资产
        Index('idx_soc_assets_expected_eol', 'expected_eol',
              postgresql_where='expected_eol IS NOT NULL'),
        # public_ip 防一 IP 挂多资产（NULL 不受约束）
        Index('uq_soc_assets_public_ip', 'public_ip', unique=True,
              postgresql_where='public_ip IS NOT NULL'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    network_segment = Column(String(50), nullable=False, default="default")
    network_zone = Column(String(50), default="other")
    asset_ip = Column(Text, nullable=False)
    # 互联网暴露面扫描用：公网 IP（云上资产 asset_ip 是内网 IP，如 ECS；内网资产保持 NULL）。
    # central_scan_scheduler public 模式自动汇总此字段，而非 asset_ip
    public_ip = Column(Text)
    asset_description = Column(Text)
    asset_status = Column(String)
    status_updated_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # 数据同步相关字段
    data_source = Column(String(20), default="manual")  # 'manual', 'wazuh', 'tplink-router'
    last_synced_at = Column(DateTime(timezone=True))
    os_name = Column(String(100))
    os_version = Column(String(100))
    hardware_info = Column(JSONB)

    name = Column(String(255))
    mac_address = Column(MACADDR)
    asset_type = Column(String(50), default="other")
    # === 重要性三维分解（治本方案 · 2026-09-14）===========================
    # 第一性原理（ISO 27005 / NIST SP 800-30 / 等保 2.0）：
    #   业务影响(BIA) + 数据敏感度(CIA) + 等保等级
    # 三个维度独立、各 5 档、互不重叠。详见 app/core/criticality.py。
    #
    # business_impact：业务影响维度（5 档 core/important/normal/auxiliary/ignorable）
    #   - 驱动：处置 SLA、推送优先级、应急响应
    #   - 不进风险评分公式
    business_impact = Column(
        String(20),
        nullable=False,
        default="normal",
        server_default="normal",
        comment="业务影响 5 档 core/important/normal/auxiliary/ignorable，详见 app/core/criticality.py",
    )
    # data_sensitivity：数据敏感度（CIA 维度，5 档 extreme/high/medium/low/negligible）
    #   - 驱动：风险评分加权因子（F1.1 替代原 criticality 加权）
    #   - 与 vulnerability_ai/asset_risk 消费的口径一致
    data_sensitivity = Column(
        String(20),
        nullable=False,
        default="medium",
        server_default="medium",
        comment="数据敏感度 5 档 extreme/high/medium/low/negligible，进风险评分",
    )
    # protection_level：等保等级（5 档 level_5~level_1，合规锚点）
    #   - 业务系统有则资产继承；无则默认 level_2
    protection_level = Column(
        String(20),
        nullable=False,
        default="level_2",
        server_default="level_2",
        comment="等保等级 5 档 level_5~level_1，合规报告/等保检查用",
    )

    # criticality：DEPRECATED（2026-09-14 起 6 个月过渡期）
    # 保留为 read-only alias，写入路径已关闭。外部读时自动从 data_sensitivity 派生。
    # 6 个月后（约 2027-03-14）由迁移 op.drop_column 清除。
    criticality = Column(
        String(20),
        default="medium",
        comment="DEPRECATED: 改用 business_impact + data_sensitivity + protection_level 三维度，读时自动从 data_sensitivity 派生",
    )
    owner = Column(String(255))
    business_unit = Column(String(255))
    wazuh_agent_id = Column(String(100))

    # P3/F3.2 §7.0 WO-0e（2026-09-13）：parent_id 已由迁移 t3u4v5w6x7y8 改为
    # UUID + FK self-reference（虚拟机/容器→宿主机）。模型侧必须同步声明，
    # 否则 alembic autogenerate 会把 DB 里现有的 UUID 列当新增、产生 drop+recreate。
    parent_id = Column(UUID(as_uuid=True), ForeignKey("soc_assets.id", ondelete="SET NULL"), nullable=True)


    # 合规 + 应急联系字段(详情页 v2 引入)
    data_classification = Column(String(20), default="internal")  # public/internal/confidential/secret
    owner_contact = Column(String(50))  # 负责人联系电话

    # T3（2026-08-15）：暴露面等级，供漏洞 AI 评分（vulnerability_ai.EXPOSURE_SCORES）使用。
    # DB 列已由迁移 b2c4d6e7f8a9 建好（NOT NULL 默认 'internal'），此处仅为 ORM 补声明，
    # 否则 ai-suggestions / score-breakdown 访问 Asset.exposure_level 即 AttributeError → 500。
    # 取值：public（公网暴露）/ internal（内网）/ isolated（隔离网络）
    exposure_level = Column(String(20), default="internal", server_default="internal")

    # P3/F1.1（2026-08-21，PRD v1.2.1）：AI 资产风险评分（规则引擎计算，不调 GLM）
    # risk_score: 0-100；NULL 表示未评分或数据全缺失（N/A，不误导为"0 分很安全"）
    risk_score = Column(Integer)
    risk_summary = Column(Text)      # GLM 一句话摘要（仅 score>=60 或快速上升资产，24h 缓存）
    risk_scored_at = Column(DateTime(timezone=True))
    score_breakdown = Column(JSONB)  # 各维度得分/权重/命中规则（可解释性，PRD §八-C）

    # P3/F3.2（2026-08-21，PRD v1.2.1）：资产生命周期
    purchase_date = Column(Date)                       # 采购日期
    warranty_end = Column(Date)                        # 保修到期
    expected_eol = Column(Date)                        # 预期 EOL（preset 自动匹配 / manual 手动覆盖）
    expected_eol_source = Column(String(20), default="preset", server_default="preset")

    # v1（图谱 G1）：责任人外键化（迁移 t3u4v5w6x7y8 已建）。
    # ⚠️ soc_users.id 为 Integer（非 UUID）。
    owner_id = Column(Integer, ForeignKey("soc_users.id", ondelete="SET NULL"), nullable=True)

    # 关系
    ports = relationship("AssetPort", backref="asset", cascade="all, delete-orphan")
    tags = relationship("AssetTag", backref="asset", cascade="all, delete-orphan")
    # 责任人（user 关系引用 user.py 中的 User）
    owner_user = relationship("User", foreign_keys=[owner_id])
    # 业务系统归属
    business_links = relationship("AssetBusiness", back_populates="asset",
                                  cascade="all, delete-orphan")

    # 关系 - 暂时注释掉，因为soc_asset_incidents表不存在
    # incidents = relationship("AssetIncident", back_populates="asset")

    def __repr__(self):
        return f"<Asset(id={self.id}, name={self.name}, ip={self.asset_ip})>"
