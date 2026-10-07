"""
资产组件模型（OH-1.4 / 方案3：syscollector packages 物化落表）

对应本体 asset-component（SBOM 级组件，用于漏洞匹配与降误报）。
数据源：OpenSearch wazuh-states-inventory-packages-*（状态快照语义），
由 asset_component_sync 定期全量刷新（按 asset 先删后插）。
"""

from sqlalchemy import Column, String, Text, DateTime, BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.models.base import Base


class AssetComponent(Base):
    """资产组件表（SBOM）"""
    __tablename__ = "soc_asset_components"
    __table_args__ = (
        UniqueConstraint('asset_id', 'name', 'version', 'component_type',
                         name='uq_asset_component'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    asset_id = Column(UUID(as_uuid=True), ForeignKey('soc_assets.id', ondelete='CASCADE'),
                      nullable=False, index=True)
    # 来源 agent（冗余存储，便于按 agent 反查与排查同步问题）
    agent_id = Column(String(64), nullable=True)
    name = Column(Text, nullable=False)
    version = Column(Text, nullable=True)
    # ecosystem：deb / rpm / pypi / npm / maven / docker / other
    component_type = Column(String(32), nullable=False, default='other')
    size = Column(BigInteger, nullable=True)
    path = Column(Text, nullable=True)
    first_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_seen = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<AssetComponent(asset_id={self.asset_id}, name={self.name}, version={self.version})>"
