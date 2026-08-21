"""
EOL 参考表模型（PRD F3.2 / v1.2.1）

预置生命周期参考表：pattern 对「规范化后的 os_name+os_version」做子串匹配
（最长模式优先），命中即回填 soc_assets.expected_eol（source=preset）。
用户手动覆盖优先（expected_eol_source='manual'），刷新不触碰。
数据来源：endoflife.date 等公开数据 + 人工维护（PRD：防幻觉主路径，WebSearch 不参与判定）。
"""
from sqlalchemy import Column, String, Date, Text, Boolean, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models.base import Base


class EolReference(Base):
    """EOL 参考表（soc_eol_reference）"""

    __tablename__ = "soc_eol_reference"
    __table_args__ = (
        Index("idx_soc_eol_ref_enabled", "enabled"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    pattern = Column(String(100), nullable=False)        # 规范化小写子串，如 "ubuntu 24.04"
    display_name = Column(String(100), nullable=False)   # 展示名，如 "Ubuntu 24.04 LTS"
    eol_date = Column(Date, nullable=False)
    source = Column(String(20), default="preset")        # preset / manual（条目维护来源）
    notes = Column(Text)                                 # 口径说明（如 Windows 按具体版本估算）
    enabled = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<EolReference(pattern={self.pattern!r}, eol={self.eol_date})>"
