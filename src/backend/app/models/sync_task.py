"""
同步任务模型
"""
from sqlalchemy import Column, String, Integer, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from app.models.base import Base


class SyncTask(Base):
    """同步任务表"""
    __tablename__ = "sync_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    sync_type = Column(String(20), nullable=False)  # 'manual', 'webhook', 'scheduled'
    status = Column(String(20), nullable=False, default="pending")  # 'pending', 'running', 'completed', 'failed'
    total_count = Column(Integer, nullable=False, default=0)
    created_count = Column(Integer, nullable=False, default=0)
    updated_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<SyncTask(id={self.id}, type={self.sync_type}, status={self.status})>"
