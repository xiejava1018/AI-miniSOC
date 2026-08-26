"""
数据同步 Schema

定义 Collector → AI-miniSOC 的通用数据同步请求/响应格式。
支持多种数据类型：asset / vulnerability / baseline / port
"""

from pydantic import BaseModel, Field
from typing import Optional


class DataSyncRequest(BaseModel):
    """通用数据同步请求 — 由 Collector 调用"""

    source: str = Field(
        ...,
        description="数据来源标识，如 tplink-router / wazuh / nmap / openvas",
    )
    data_type: str = Field(
        ...,
        description="数据类型: asset / vulnerability / baseline / port",
    )
    items: list[dict] = Field(
        ...,
        description="数据列表，每个 dict 的字段结构取决于 data_type",
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="可选元信息（采集耗时、原始条数等）",
    )


class DataSyncResponse(BaseModel):
    """通用数据同步响应"""

    message: str
    data_type: str
    source: str
    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)
    # P3 资产扫描（P2-T4 死信机制）：每条 handle 返回的死信 batch id（全部成功时为 None）
    dead_letter_batch_id: Optional[str] = None
