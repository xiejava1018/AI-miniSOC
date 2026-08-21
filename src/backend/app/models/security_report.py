"""
AI 安全报告模型（PRD P3 / F2.2）

按 PRD §F2.2 表结构落，附加：
  - triggered_by: VARCHAR(64) 存 username 快照或 'system:scheduler'，
    与现有审计/反馈字段惯例一致（ProjectPreferencesDict: VARCHAR > FK）
  - trigger_meta: JSONB 存事件驱动触发时的 critical_high_count 等溯源字段

触发方式：weekly/monthly/on_demand/incident_driven
数据完整性：data_coverage JSONB 必填，硬门槛——生成前显式记录窗口与缺口
"""
from sqlalchemy import Column, String, DateTime, Text, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func

from app.models.base import Base


# 与 PRD §F2.2 一致；incident_driven 是 v1.2 新增的事件驱动类型
TYPE_WEEKLY = "weekly"
TYPE_MONTHLY = "monthly"
TYPE_ON_DEMAND = "on_demand"
TYPE_INCIDENT_DRIVEN = "incident_driven"
REPORT_TYPES = {TYPE_WEEKLY, TYPE_MONTHLY, TYPE_ON_DEMAND, TYPE_INCIDENT_DRIVEN}


class SecurityReport(Base):
    """AI 安全报告（soc_security_reports）"""

    __tablename__ = "soc_security_reports"
    __table_args__ = (
        # 列表按时间倒序
        Index("idx_soc_security_reports_created", "created_at"),
        # 按类型过滤
        Index("idx_soc_security_reports_type_created", "report_type", "created_at"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())

    report_type = Column(String(20), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    title = Column(String(255))

    # AI 产物
    summary = Column(Text)                # 执行摘要
    content = Column(JSONB)               # 章节 {overview, trends, risks, recommendations, data_notes}
    risk_highlights = Column(Text)        # 高亮风险（Markdown 友好列表）
    recommendations = Column(Text)        # 处置建议

    # 硬门槛：数据完整性说明（窗口/缺口/源状态）；即使模板降级也必须填
    data_coverage = Column(JSONB, nullable=False)

    # 溯源（X2 可追溯性）
    prompt_version = Column(String(20))   # 如 'security-report-v1'
    triggered_by = Column(String(64))     # username 或 'system:scheduler'
    trigger_meta = Column(JSONB)          # 事件驱动时存 {critical_high_count, threshold}

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    def __repr__(self):
        return f"<SecurityReport(id={self.id}, type={self.report_type}, period={self.period_start}~{self.period_end})>"