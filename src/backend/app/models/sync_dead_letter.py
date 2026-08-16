"""
同步死信队列表模型（P2-T4）

失败记录入死信，支持按批次重放。
"""
from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.models.base import Base


class SyncDeadLetter(Base):
    """同步失败明细 / 死信队列表（soc_sync_dead_letter）"""
    __tablename__ = "soc_sync_dead_letter"

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    batch_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    source = Column(String(100), nullable=False)
    data_type = Column(String(50), nullable=False)
    item_index = Column(Integer, nullable=False)
    item_key = Column(String(255))
    error_class = Column(String(100))
    error_message = Column(Text)
    raw_item = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    replay_count = Column(Integer, nullable=False, default=0)
    last_replayed_at = Column(DateTime(timezone=True))
    resolved = Column(Boolean, nullable=False, default=False)

    def __repr__(self):
        return (
            f"<SyncDeadLetter(batch={self.batch_id}, source={self.source}, "
            f"item_idx={self.item_index}, resolved={self.resolved})>"
        )