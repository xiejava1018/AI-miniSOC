"""AI Provider 模型（多 AI 模型配置，2026-09-13 独立化拆分）

设计：AI Provider 与数据源是两类业务配置——数据源是"被采集的安全数据输入"，
AI Provider 是"平台智能能力底座"。表结构独立，机制（Fernet 加密 / 默认实例 /
测试连接三件套）沿用数据源管理的成熟模式。

scenes 场景路由（JSONB 数组）：消费点经 ai_client.ai_chat(scene=...) 调用，
resolve_ai 按 场景精确匹配 → 默认实例 → env GLM_* 回落。
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.models.base import Base


class AIProvider(Base):
    __tablename__ = "soc_ai_providers"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    provider_code = Column(String(64), nullable=False, unique=True)  # 如 glm-main / deepseek
    name = Column(String(200), nullable=False)
    base_url = Column(String(512), nullable=False)  # OpenAI 兼容 base_url，不以 / 结尾
    protocol = Column(String(32), nullable=False, default="openai")  # openai（当前唯一）
    model_name = Column(String(200), nullable=False)  # 如 glm-4-flash / deepseek-chat
    api_key = Column(Text, nullable=True)  # Fernet 加密；出参永不返回
    scenes = Column(JSONB, nullable=False, server_default="[]")  # ["report","asset_query"]
    max_tokens = Column(Integer, nullable=True)  # 空 = 不限
    timeout_seconds = Column(Integer, nullable=False, default=60)
    enabled = Column(Boolean, nullable=False, default=True)
    is_default = Column(Boolean, nullable=False, default=False)  # 同表至多一个
    remark = Column(String(500), nullable=True)
    last_test_at = Column(DateTime(timezone=True), nullable=True)
    last_test_ok = Column(Boolean, nullable=True)
    last_test_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_ai_providers_enabled", "enabled"),
    )
