"""
AI 反馈模型（PRD F4.1 / v1.2 §5.3）

所有 AI 产物（风险摘要/态势摘要/NL 查询/报告/知识条目）统一附 👍/👎 反馈。
月度按 target_type 汇总，👎 率 > 20% 触发 Prompt 迭代评审（运营流程，非代码）。

注：user_id 为 Integer，对齐 soc_users.id（PRD 草案写 UUID，实现时对齐现实 schema）。
"""
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.models.base import Base


class AiFeedback(Base):
    """AI 反馈表（soc_ai_feedback）"""

    __tablename__ = "soc_ai_feedback"
    __table_args__ = (
        Index("idx_soc_ai_feedback_target", "target_type", "target_id"),
        Index("idx_soc_ai_feedback_created", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    # 产物类型：risk_summary / security_summary / query / report / knowledge
    target_type = Column(String(50), nullable=False)
    # 关联产物 ID（资产ID/报告ID/会话ID/知识ID，字符串化存取）
    target_id = Column(String(100), nullable=False)
    rating = Column(String(10), nullable=False)  # up / down
    comment = Column(Text)                       # 用户修正文本（可选）
    user_id = Column(Integer, ForeignKey("soc_users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<AiFeedback(target={self.target_type}:{self.target_id}, rating={self.rating})>"
