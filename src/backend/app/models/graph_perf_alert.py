"""GraphPerfAlert 模型（图谱 P95 性能告警，OH-3.7）。

表 soc_graph_perf_alerts 由 alembic c7d8e9f10a2b 用 raw SQL 创建。
这里补 ORM 是为了让 Base.metadata.create_all / alembic check 在测试库
（AI-miniSOC-db_test）也能建出这张表——避免 ``tests/test_graph_perf_alerts.py``
中 conftest.db_session 走 Base.metadata.create_all 时漏表。

设计依据：docs/design/2026-09-30-资产管理AI能力建设方案.md §5.4 / §7.3
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Index, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SOCGraphPerfAlert(Base):
    """图谱 P95 性能告警事件表（sysadmin 视角）。"""

    __tablename__ = "soc_graph_perf_alerts"

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=uuid4)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    query_type: Mapped[str] = mapped_column(String(32), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    triggered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_size: Mapped[int] = mapped_column(Integer, nullable=False)
    p50_ms: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    p95_ms: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    max_ms: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    slow_count: Mapped[int] = mapped_column(Integer, nullable=False)
    threshold_ms: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    meta: Mapped[dict] = mapped_column(
        "metadata",  # SQL 列名仍是 metadata（避免与 SQLAlchemy MetaData 冲突）
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        Index(
            "idx_soc_graph_perf_alerts_unresolved",
            "resolved",
            "triggered_at",
        ),
        Index(
            "idx_soc_graph_perf_alerts_query",
            "query_type",
            "severity",
            "triggered_at",
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SOCGraphPerfAlert id={self.id} alert_type={self.alert_type} "
            f"severity={self.severity} resolved={self.resolved}>"
        )
