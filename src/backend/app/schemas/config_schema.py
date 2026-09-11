"""配置 Schema Schemas"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConfigSchemaResponse(BaseModel):
    id: int
    category: str
    key: str
    label: str
    value_type: str
    default_value: Optional[str] = None
    options: Optional[List[Dict[str, Any]]] = None
    validation: Optional[Dict[str, Any]] = None
    effect_scope: str
    sensitive: bool
    group_name: Optional[str] = None
    sort_order: int
    help_text: Optional[str] = None
    editable: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class ConfigSchemaGroup(BaseModel):
    """按 category 分组的配置项"""

    category: str
    count: int
    items: List[ConfigSchemaResponse]


class ConfigSchemaListResponse(BaseModel):
    items: List[ConfigSchemaResponse]
    groups: List[ConfigSchemaGroup]