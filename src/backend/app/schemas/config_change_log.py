"""配置变更审计 Schemas"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConfigChangeLogResponse(BaseModel):
    id: int
    target_type: str
    target_key: str
    action: str
    before_value: Optional[str] = None
    after_value: Optional[str] = None
    changed_fields: Optional[List[str]] = None
    operator_id: Optional[int] = None
    operator_ip: Optional[str] = None
    result: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ConfigChangeLogListResponse(BaseModel):
    total: int
    items: List[ConfigChangeLogResponse]
    page: int
    page_size: int