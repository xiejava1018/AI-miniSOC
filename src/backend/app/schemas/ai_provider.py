"""AI Provider Schema（多 AI 模型配置）"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

PROVIDER_CODE_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"

SCENES: List[Dict[str, str]] = [
    {"value": "asset_query", "label": "资产 AI 查询"},
    {"value": "report", "label": "安全报告"},
    {"value": "impact", "label": "变更影响分析"},
    {"value": "ai_analysis", "label": "告警研判"},
    {"value": "compliance", "label": "合规 AI 解读"},
    {"value": "knowledge", "label": "知识库"},
    {"value": "risk", "label": "风险评分"},
    {"value": "reconcile", "label": "稽核 AI"},
    {"value": "behavior", "label": "行为画像"},
]
SCENE_VALUES = [s["value"] for s in SCENES]


class AIProviderCreate(BaseModel):
    provider_code: str = Field(..., description="实例编码，如 glm-main / deepseek")
    name: str = Field(..., min_length=1, max_length=200)
    base_url: str = Field(..., min_length=1, max_length=512, description="OpenAI 兼容 base_url")
    protocol: str = Field(default="openai")
    model_name: str = Field(..., min_length=1, max_length=200)
    api_key: Optional[str] = Field(default=None, description="仅写；编辑时留空表示不修改")
    scenes: List[str] = Field(default_factory=list, description="场景路由")
    max_tokens: Optional[int] = Field(default=None, ge=64, le=131072)
    timeout_seconds: int = Field(default=60, ge=5, le=300)
    enabled: bool = True
    is_default: bool = False
    remark: Optional[str] = Field(default=None, max_length=500)

    @field_validator("provider_code")
    @classmethod
    def _validate_code(cls, v: str) -> str:
        import re

        if not re.match(PROVIDER_CODE_PATTERN, v):
            raise ValueError("编码只能包含小写字母、数字和连字符，3-64 位")
        return v

    @field_validator("base_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("地址需以 http:// 或 https:// 开头")
        if v.endswith("/"):
            raise ValueError("地址结尾不应包含 /")
        return v

    @field_validator("scenes")
    @classmethod
    def _validate_scenes(cls, v: List[str]) -> List[str]:
        bad = [s for s in v if s not in SCENE_VALUES]
        if bad:
            raise ValueError(f"未知场景: {bad}；合法值: {SCENE_VALUES}")
        return v


class AIProviderUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    base_url: Optional[str] = None
    protocol: Optional[str] = None
    model_name: Optional[str] = None
    api_key: Optional[str] = None
    scenes: Optional[List[str]] = None
    max_tokens: Optional[int] = Field(default=None, ge=64, le=131072)
    timeout_seconds: Optional[int] = Field(default=5, ge=5, le=300)
    enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    remark: Optional[str] = None

    @field_validator("base_url")
    @classmethod
    def _validate_url(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("地址需以 http:// 或 https:// 开头")
        if v.endswith("/"):
            raise ValueError("地址结尾不应包含 /")
        return v

    @field_validator("scenes")
    @classmethod
    def _validate_scenes(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is None:
            return v
        bad = [s for s in v if s not in SCENE_VALUES]
        if bad:
            raise ValueError(f"未知场景: {bad}")
        return v


class AIProviderResponse(BaseModel):
    id: int
    provider_code: str
    name: str
    base_url: str
    protocol: str
    model_name: str
    has_key: bool = False
    scenes: List[str] = []
    max_tokens: Optional[int] = None
    timeout_seconds: int = 60
    enabled: bool
    is_default: bool
    remark: Optional[str] = None
    last_test_at: Optional[datetime] = None
    last_test_ok: Optional[bool] = None
    last_test_message: Optional[str] = None

    model_config = {"from_attributes": True}


class AIProviderListResponse(BaseModel):
    items: List[AIProviderResponse]
    total: int


class AITestRequest(BaseModel):
    """测试连接：id（已存实例）或 draft（表单草稿）二选一。"""

    id: Optional[int] = None
    draft: Optional[AIProviderCreate] = None


class AITestCheck(BaseModel):
    name: str
    ok: bool
    message: str


class AITestResponse(BaseModel):
    ok: bool
    latency_ms: int = 0
    message: str
    checks: List[AITestCheck] = []
    details: Dict[str, Any] = {}


class AISceneCatalog(BaseModel):
    """场景目录（供前端渲染多选）。"""

    scenes: List[Dict[str, str]]
