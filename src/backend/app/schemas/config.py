"""Config Schemas"""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, Any


class ConfigItem(BaseModel):
    """配置项"""
    key: str = Field(..., min_length=1, max_length=100, description="配置键")
    value: Any = Field(..., description="配置值")
    description: Optional[str] = Field(None, max_length=500, description="描述")
    category: Optional[str] = Field(None, max_length=50, description="分类")


class ConfigResponse(BaseModel):
    """配置响应"""
    id: int = Field(..., description="配置ID")
    key: str = Field(..., description="配置键")
    value: str = Field(..., description="配置值")
    description: Optional[str] = Field(None, description="描述")
    category: Optional[str] = Field(None, description="分类")
    is_sensitive: bool = Field(..., description="是否敏感")
    created_at: str = Field(..., description="创建时间")
    updated_at: str = Field(..., description="更新时间")

    class Config:
        from_attributes = True


class ConfigUpdate(BaseModel):
    """更新配置"""
    value: Any = Field(..., description="配置值")
    description: Optional[str] = Field(None, max_length=500, description="描述")


class TestSmtpRequest(BaseModel):
    """测试SMTP请求"""
    host: str = Field(..., min_length=1, max_length=200, description="SMTP主机")
    port: int = Field(..., ge=1, le=65535, description="SMTP端口")
    username: str = Field(..., min_length=1, max_length=100, description="用户名")
    password: str = Field(..., min_length=1, max_length=200, description="密码")
    from_email: EmailStr = Field(..., description="发件人邮箱")
    to_email: EmailStr = Field(..., description="收件人邮箱")
    use_tls: bool = Field(default=True, description="使用TLS")


class TestWebhookRequest(BaseModel):
    """测试Webhook请求"""
    url: str = Field(..., min_length=1, max_length=500, description="Webhook URL")
    method: str = Field(default="POST", pattern=r'^(GET|POST|PUT)$', description="HTTP方法")
    headers: Optional[dict[str, str]] = Field(None, description="请求头")
    body: Optional[dict[str, Any]] = Field(None, description="请求体")
