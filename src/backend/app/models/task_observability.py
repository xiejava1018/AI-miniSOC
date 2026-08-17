"""
后台任务可观测性模型（v0.4.2 Phase 1.1）

- SocTaskRegistry：每任务一行（定义 + 当前态）
- SocTaskRun：每执行一行（真历史 + 独立进度心跳）
- TaskRunStatus：状态枚举

参考设计文档：docs/design/2026-08-16-后台任务执行可观测性梳理与方案-v0.4.md
"""
from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.models.base import Base


class TaskRunStatus(str, enum.Enum):
    """任务 run 的状态机。

    流转：
        pending → running → success
                            → failed
                            → timeout (代码最终完成但业务超过 timeout_s)
                            → skipped (拿不到进程内锁)
        running → zombie (看门狗标记，进程消失)
        running → unknown (启动对账，上次异常退出)
    """

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"
    ZOMBIE = "zombie"
    UNKNOWN = "unknown"


class SocTaskRegistry(Base):
    """每任务一行的定义 + 当前态（soc_task_registry）。"""

    __tablename__ = "soc_task_registry"

    task_key = Column(String(100), primary_key=True)
    task_name = Column(String(200), nullable=False)
    task_type = Column(
        String(20),
        CheckConstraint(
            "task_type IN ('scheduled', 'async', 'thread', 'watchdog')",
            name="ck_task_registry_type",
        ),
        nullable=False,
    )
    owner_module = Column(String(200))
    schedule_expr = Column(String(100))  # 描述用，例如 "@every 5m"
    expected_interval_s = Column(Integer)
    timeout_s = Column(Integer, nullable=False, default=360)
    enabled = Column(Boolean, nullable=False, default=True)

    # 当前态
    # 注：不使用 ForeignKey 约束，避免与 soc_task_runs.task_key 的 FK 形成循环依赖。
    # 应用层保证 current_run_id 指向有效的 run；run 被删时这里可以变悬挂，但读侧处理。
    current_run_id = Column(UUID(as_uuid=True), nullable=True)
    lock_owner = Column(String(200))  # host:pid（仅 Phase 2 多 pod 用，Phase 1 留空）
    last_run_at = Column(DateTime(timezone=True))
    last_status = Column(
        SAEnum(
            TaskRunStatus,
            name="task_run_status_v1",
            native_enum=False,
            length=20,
            values_callable=lambda x: [e.value for e in x],
        ),
    )
    last_error = Column(Text)
    last_duration_ms = Column(Integer)
    last_stats = Column(JSONB)
    consecutive_failures = Column(Integer, nullable=False, default=0)
    total_runs = Column(BigInteger, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<SocTaskRegistry(key={self.task_key}, type={self.task_type}, "
            f"enabled={self.enabled}, consecutive_failures={self.consecutive_failures})>"
        )


class SocTaskRun(Base):
    """每执行一行的真历史（soc_task_runs）。"""

    __tablename__ = "soc_task_runs"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    task_key = Column(
        String(100),
        ForeignKey("soc_task_registry.task_key", ondelete="SET NULL"),
        nullable=False,
    )
    trigger = Column(
        String(20),
        CheckConstraint(
            "trigger IN ('scheduled', 'manual', 'api', 'replay', 'startup', 'watchdog')",
            name="ck_task_runs_trigger",
        ),
        nullable=False,
    )
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    finished_at = Column(DateTime(timezone=True))
    status = Column(
        SAEnum(
            TaskRunStatus,
            name="task_run_status_v1",
            native_enum=False,
            length=20,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    duration_ms = Column(Integer)
    error_text = Column(Text)
    stats_json = Column(JSONB)
    total = Column(Integer)
    processed = Column(Integer)
    percent = Column(Integer)
    # ★ v0.4 P1-1：进度心跳挪到 runs 行（每 run 独立），不在 registry
    last_progress_at = Column(DateTime(timezone=True))
    correlation_id = Column(String(100))
    host = Column(String(200))
    triggered_by_user = Column(String(200))
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        Index("ix_task_runs_taskkey_started", "task_key", "started_at", postgresql_using="btree"),
        # 部分索引：仅 running 行参与 zombie 扫描
        Index(
            "ix_task_runs_running_partial",
            "started_at",
            postgresql_where=(status == "running"),
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<SocTaskRun(id={self.id}, task={self.task_key}, status={self.status}, "
            f"started={self.started_at})>"
        )
