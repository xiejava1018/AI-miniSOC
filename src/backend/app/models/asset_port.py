"""
资产端口模型
"""

from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, INET, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text
from app.models.base import Base


class AssetPort(Base):
    """资产端口表"""
    __tablename__ = "soc_asset_ports"
    __table_args__ = (
        UniqueConstraint('asset_ip', 'port', 'protocol', name='unique_asset_port'),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    asset_id = Column(UUID(as_uuid=True), ForeignKey('soc_assets.id', ondelete='CASCADE'), nullable=True)
    asset_ip = Column(INET, nullable=False)
    port = Column(Integer, nullable=False)
    protocol = Column(String(10), nullable=False, default='tcp')  # tcp, udp
    state = Column(String(20), nullable=False, default='open')  # open, closed, filtered
    service = Column(String(100), nullable=True)
    version = Column(Text, nullable=True)
    scan_time = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    service_banner = Column(Text, nullable=True)
    vulnerability = Column(Text, nullable=True)
    vulnerabilities = Column(JSONB, nullable=True, server_default=text("'[]'::jsonb"))
    # P4-B-α：JSONB 存 vulners 返回的 CVE 列表（如 ["CVE-2024-12345", "CVE-2023-67890"]）
    # 与 vulnerability (Text 单条描述) 并存；后续 unified 处理待 P5
    last_seen = Column(DateTime(timezone=True), nullable=True, server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AssetPort(asset_ip={self.asset_ip}, port={self.port}, protocol={self.protocol}, state={self.state})>"
