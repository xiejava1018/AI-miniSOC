"""
资产数据来源模型

记录资产与数据来源的多对多关系。
一个资产可以被多个来源（Wazuh、路由器、Nmap 等）观察到，
每个来源有自己看到的状态和特有数据。
"""

from sqlalchemy import Column, String, Text, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from app.models.base import Base


class AssetSource(Base):
    """资产数据来源表"""
    __tablename__ = "soc_asset_sources"
    __table_args__ = (
        UniqueConstraint('asset_id', 'source', name='uq_asset_source'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    asset_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # 来源标识
    source = Column(String(50), nullable=False)  # 'wazuh' / 'tplink-router' / 'nmap' / 'manual'

    # 来源系统内的标识（如 Wazuh agent_id）
    source_id = Column(Text)

    # 来源视角的设备状态
    source_status = Column(String(20))  # 各来源自己看到的状态

    # 该来源最后一次看到此资产的时间
    last_seen_at = Column(DateTime(timezone=True))

    # 来源特有的数据（各来源不同）
    # 路由器: {ssid, rssi, ap_name, conn_type, up_speed, down_speed}
    # Wazuh:  {os_name, os_version, agent_version}
    # Nmap:   {scan_technique, scan_time}
    source_metadata = Column(JSONB)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
