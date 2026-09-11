"""数据源 Schemas（Pydantic）

设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §5.3

安全约束：
  - DataSourceResponse 绝不出现 auth_secret 明文/密文（Pydantic 不声明即可）
  - DataSourceUpdate 中 auth_secret 留空 / None 表示不修改原值
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator


SOURCE_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,63}$")

# source_type 枚举（与 §11.2 对齐；前端共用）
SOURCE_TYPES: List[Dict[str, Any]] = [
    {"value": "wazuh", "label": "Wazuh", "auth_types": ["basic"], "default_port": 55000},
    {
        "value": "opensearch",
        "label": "OpenSearch",
        "auth_types": ["basic", "none"],
        "default_port": 9200,
    },
    {
        "value": "loki",
        "label": "Loki",
        "auth_types": ["none", "token"],
        "default_port": 3100,
    },
    {
        "value": "tplink",
        "label": "TP-Link 路由器",
        "auth_types": ["basic"],
        "default_port": 80,
    },
    {
        "value": "scanner",
        "label": "扫描器",
        "auth_types": ["apikey", "none"],
        "default_port": 8000,
    },
]
SOURCE_TYPE_VALUES = [t["value"] for t in SOURCE_TYPES]
AUTH_TYPE_VALUES = ["basic", "token", "apikey", "none"]


class DataSourceBase(BaseModel):
    source_code: str = Field(
        ...,
        min_length=3,
        max_length=64,
        description="数据源编码；小写字母、数字与连字符，3-64 位",
    )
    source_type: str = Field(..., description="数据源类型")
    name: str = Field(..., min_length=1, max_length=200)
    endpoint: str = Field(..., min_length=1, max_length=512)
    auth_type: Literal["basic", "token", "apikey", "none"] = Field(
        default="none", description="认证方式"
    )
    auth_username: str | None = Field(default=None, max_length=200)
    auth_secret: str | None = Field(
        default=None, description="密码/密钥（仅写）；编辑时留空表示不修改"
    )
    verify_ssl: bool = Field(default=False)
    timeout_seconds: int = Field(default=30, ge=1, le=300)
    retry_times: int = Field(default=3, ge=0, le=10)
    retry_backoff_seconds: int = Field(default=2, ge=1, le=60)
    enabled: bool = Field(default=True)
    is_default: bool = Field(default=False)
    config_json: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_code")
    @classmethod
    def _validate_source_code(cls, v: str) -> str:
        if not SOURCE_CODE_PATTERN.match(v or ""):
            raise ValueError("编码只能包含小写字母、数字和连字符，3-64 位")
        return v

    @field_validator("source_type")
    @classmethod
    def _validate_source_type(cls, v: str) -> str:
        if v not in SOURCE_TYPE_VALUES:
            raise ValueError(f"不支持的 source_type：{v}")
        return v

    @field_validator("endpoint")
    @classmethod
    def _validate_endpoint(cls, v: str) -> str:
        if not v or not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("地址需以 http:// 或 https:// 开头")
        if v.endswith("/"):
            raise ValueError("地址结尾不应包含 /")
        return v


class DataSourceCreate(DataSourceBase):
    """新增数据源"""


class DataSourceUpdate(BaseModel):
    """更新数据源（全部可选；auth_secret 留空/None 表示不修改）"""

    source_type: str | None = Field(default=None)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    endpoint: str | None = Field(default=None, min_length=1, max_length=512)
    auth_type: Literal["basic", "token", "apikey", "none"] | None = None
    auth_username: str | None = None
    auth_secret: str | None = Field(
        default=None, description="留空/None 表示不修改原值"
    )
    verify_ssl: bool | None = None
    timeout_seconds: int | None = Field(default=None, ge=1, le=300)
    retry_times: int | None = Field(default=None, ge=0, le=10)
    retry_backoff_seconds: int | None = Field(default=None, ge=1, le=60)
    enabled: bool | None = None
    is_default: bool | None = None
    config_json: Dict[str, Any] | None = None

    @field_validator("source_type")
    @classmethod
    def _validate_source_type(cls, v: str | None) -> str | None:
        if v is not None and v not in SOURCE_TYPE_VALUES:
            raise ValueError(f"不支持的 source_type：{v}")
        return v

    @field_validator("endpoint")
    @classmethod
    def _validate_endpoint(cls, v: str | None) -> str | None:
        if v is None:
            return v
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("地址需以 http:// 或 https:// 开头")
        if v.endswith("/"):
            raise ValueError("地址结尾不应包含 /")
        return v


class DataSourceResponse(BaseModel):
    """数据源出参（绝不包含 auth_secret）"""

    id: int
    source_code: str
    source_type: str
    name: str
    endpoint: str
    auth_type: str
    auth_username: str | None = None
    has_secret: bool = Field(default=False, description="是否已设置密钥")
    secret_masked: str = Field(default="", description="密钥脱敏占位（编辑态展示）")
    verify_ssl: bool
    timeout_seconds: int
    retry_times: int
    retry_backoff_seconds: int
    enabled: bool
    is_default: bool
    config_json: Dict[str, Any] = Field(default_factory=dict)
    last_test_at: datetime | None = None
    last_test_ok: bool | None = None
    last_test_message: str | None = None
    health_status: str | None = Field(
        default=None,
        description="派生字段：normal | abnormal | untested | stale",
    )
    created_at: datetime | None = None
    updated_at: datetime | None = None
    updated_by: int | None = None

    model_config = ConfigDict(from_attributes=True)


class DataSourceListResponse(BaseModel):
    total: int
    items: List[DataSourceResponse]
    page: int
    page_size: int


class DataSourceTypeItem(BaseModel):
    value: str
    label: str
    auth_types: List[str]
    default_port: int


class DataSourceTypesResponse(BaseModel):
    items: List[DataSourceTypeItem]


class TestConnectionRequest(BaseModel):
    """测试连接请求（支持两种入体：现有 id / 未保存草稿 draft）"""

    id: int | None = None
    draft: DataSourceCreate | None = None

    @field_validator("draft")
    @classmethod
    def _one_of(cls, v, info):  # type: ignore[no-untyped-def]
        data = info.data
        if (data.get("id") is None) and (v is None):
            raise ValueError("id 与 draft 必填其一")
        return v


class TestCheck(BaseModel):
    name: str
    ok: bool
    message: str


class TestConnectionResponse(BaseModel):
    ok: bool
    latency_ms: int
    message: str
    checks: List[TestCheck] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


class ResolveStatusItem(BaseModel):
    source_type: str
    origin: str  # "db:<code>" | "env" | "none"
    source_code: str | None = None
    enabled: bool
    is_default: bool


class ResolveStatusResponse(BaseModel):
    items: List[ResolveStatusItem]


class EnabledToggleRequest(BaseModel):
    enabled: bool