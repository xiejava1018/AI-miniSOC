"""
资产变更日志模型
"""
from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.models.base import Base


class AssetChangeLog(Base):
    """资产变更日志表"""
    __tablename__ = "soc_asset_change_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    asset_id = Column(UUID(as_uuid=True), ForeignKey('soc_assets.id', ondelete='CASCADE'), nullable=False)
    sync_task_id = Column(UUID(as_uuid=True), ForeignKey('soc_sync_tasks.id', ondelete='SET NULL'))
    change_type = Column(String(20), nullable=False)  # 'created', 'updated', 'status_changed'
    field_name = Column(String(50))
    old_value = Column(Text)
    new_value = Column(Text)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<AssetChangeLog(id={self.id}, asset_id={self.asset_id}, type={self.change_type})>"
