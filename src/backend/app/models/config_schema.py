"""
配置项元信息（Schema）模型

描述 ``soc_system_config`` 中每个配置项的渲染与校验元数据。
本表不替代 ``soc_system_config``，只描述其元信息 —— 配置项缺 schema
时仍以通用 KV 编辑器兜底展示，避免配置项不可见。

Schema 种子数据由 ``scripts/seed_config_schema.py`` 预置。
"""

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.models.base import Base


class ConfigSchema(Base):
    """配置项元信息表（soc_config_schema）"""

    __tablename__ = "soc_config_schema"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    category = Column(String(50), nullable=False)
    key = Column(String(100), nullable=False)
    label = Column(String(200), nullable=False)
    value_type = Column(String(20), nullable=False, default="string")
    default_value = Column(Text, nullable=True)
    options = Column(JSONB, nullable=True)  # 枚举：[{"label","value"}]
    validation = Column(JSONB, nullable=True)  # {"min","max","maxLength","pattern",...}
    effect_scope = Column(String(20), nullable=False, default="immediate")
    sensitive = Column(Boolean, nullable=False, default=False)
    group_name = Column(String(100), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    help_text = Column(Text, nullable=True)
    editable = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<ConfigSchema(id={self.id}, category={self.category}, key={self.key}, "
            f"type={self.value_type}, scope={self.effect_scope})>"
        )