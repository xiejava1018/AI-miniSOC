"""
运维知识库模型（PRD F2.3 / v1.2 §5.3）

知识来源三类：
- incident_summary：已解决事件的 AI 自动提取（故障→原因→解决方案三元组）
- ai_generated：告警分析结果沉淀（后续迭代接入）
- manual：手动录入的运维文档

老化管理（PRD v1.2）：last_validated_at 超 12 个月 → pending_review（列表标黄）；
人工 validate 刷新时间且 confidence 提升至 90。
检索：关键词召回 + GLM rerank（tsvector 为可选加速层，MVP 不启用）。
"""
from sqlalchemy import Column, String, Text, DateTime, SmallInteger, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models.base import Base


class Knowledge(Base):
    """运维知识库表（soc_knowledge_base）"""

    __tablename__ = "soc_knowledge_base"
    __table_args__ = (
        Index("idx_soc_kb_category", "category"),
        Index("idx_soc_kb_review_status", "review_status"),
        Index("idx_soc_kb_source", "source_type", "source_id"),
        Index("idx_soc_kb_updated", "updated_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)          # 结构化正文（症状/原因/解决方案）
    category = Column(String(50))                   # troubleshooting, configuration, policy, reference
    source_type = Column(String(50))                # ai_generated, manual, incident_summary
    source_id = Column(String(100))                 # 关联的事件ID/分析ID（提取去重键）
    tags = Column(Text)                             # 逗号分隔标签（MVP 简化，弃 TEXT[] 便于 ORM 通用性）
    last_validated_at = Column(DateTime(timezone=True))
    confidence_score = Column(SmallInteger, default=70)   # 人工验证后提升至 90
    review_status = Column(String(20), default="active")  # active / pending_review
    created_by = Column(String(100))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    @property
    def tag_list(self) -> list:
        return [t.strip() for t in (self.tags or "").split(",") if t.strip()]

    def __repr__(self):
        return f"<Knowledge(id={self.id}, title={self.title!r}, status={self.review_status})>"
