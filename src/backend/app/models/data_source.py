"""
数据源连接配置模型（多实例）

承载 Wazuh / OpenSearch / Loki / TP-Link / Scanner 等外部系统的连接参数。
与 ``soc_asset_sources``（资产多源溯源表）语义不同，勿混用。

设计要点：
- 同一 source_type 支持多实例，通过 is_default 标记默认；
- ``auth_secret`` Fernet 加密存储，API 出参永不返回明文或密文；
- ``source_code`` 全局唯一，便于在配置审计/解析器中以稳定字符串定位；
- ``is_default`` 的"同类型至多一个"由部分唯一索引
  ``uq_data_source_default_per_type`` 在数据库层约束（见 Alembic 迁移）。
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func, text

from app.models.base import Base


class DataSource(Base):
    """数据源连接配置表（soc_data_sources，多实例）"""

    __tablename__ = "soc_data_sources"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    source_code = Column(String(64), nullable=False, unique=True)
    source_type = Column(String(32), nullable=False)
    name = Column(String(200), nullable=False)
    endpoint = Column(String(512), nullable=False)
    auth_type = Column(String(32), nullable=False, default="none")
    auth_username = Column(String(200), nullable=True)
    auth_secret = Column(Text, nullable=True)  # Fernet 加密；仅写，不读
    verify_ssl = Column(Boolean, nullable=False, default=False)
    timeout_seconds = Column(Integer, nullable=False, default=30)
    retry_times = Column(Integer, nullable=False, default=3)
    retry_backoff_seconds = Column(Integer, nullable=False, default=2)
    enabled = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)
    config_json = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    last_test_at = Column(DateTime(timezone=True), nullable=True)
    last_test_ok = Column(Boolean, nullable=True)
    last_test_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
    updated_by = Column(BigInteger, ForeignKey("soc_users.id"), nullable=True)

    __table_args__ = (
        Index("ix_data_source_type_enabled", "source_type", "enabled"),
    )

    def __repr__(self) -> str:
        return (
            f"<DataSource(id={self.id}, code={self.source_code}, "
            f"type={self.source_type}, default={self.is_default}, enabled={self.enabled})>"
        )