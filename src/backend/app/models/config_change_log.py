"""
配置变更审计模型

记录配置变更的事实（谁在何时把什么从 A 改成 B），敏感字段值替换为 "***"。
写入失败不得阻断主流程 —— 由 ConfigAuditService 保证。
"""

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.models.base import Base


class ConfigChangeLog(Base):
    """配置变更审计表（soc_config_change_log）"""

    __tablename__ = "soc_config_change_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    target_type = Column(String(32), nullable=False)
    target_key = Column(String(200), nullable=False)
    action = Column(String(20), nullable=False)
    before_value = Column(Text, nullable=True)
    after_value = Column(Text, nullable=True)
    changed_fields = Column(JSONB, nullable=True)
    operator_id = Column(BigInteger, ForeignKey("soc_users.id"), nullable=True)
    operator_ip = Column(String(64), nullable=True)
    result = Column(String(20), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<ConfigChangeLog(id={self.id}, type={self.target_type}, "
            f"key={self.target_key}, action={self.action}, result={self.result})>"
        )