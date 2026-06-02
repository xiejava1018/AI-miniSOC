"""
核心配置管理
从环境变量读取配置
"""

from pydantic_settings import BaseSettings
from pydantic import field_validator
from typing import List, Union
from urllib.parse import quote_plus


class Settings(BaseSettings):
    """应用配置"""

    # 数据库配置
    DB_HOST: str = "192.168.0.42"
    DB_PORT: int = 5432
    DB_NAME: str = "AI-miniSOC-db"
    DB_USER: str = "postgres"
    DB_PASSWORD: str

    # 独立测试库（需先执行 CREATE DATABASE <TEST_DB_NAME>;）
    # 测试通过 conftest 走这个库，与生产数据完全隔离
    TEST_DB_NAME: str = "AI-miniSOC-db_test"

    # 数据库连接字符串
    @property
    def DATABASE_URL(self) -> str:
        # 对密码进行 URL 编码，处理特殊字符
        encoded_password = quote_plus(self.DB_PASSWORD)
        return f"postgresql://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    @property
    def TEST_DATABASE_URL(self) -> str:
        """独立测试库 URL。仅 conftest 使用，运行时业务代码不应触碰。"""
        encoded_password = quote_plus(self.DB_PASSWORD)
        return f"postgresql://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.TEST_DB_NAME}"

    # 智谱AI配置
    GLM_API_KEY: str
    GLM_MODEL: str = "glm-4-flash"
    GLM_API_BASE: str = "https://open.bigmodel.cn/api/paas/v4/"

    # JWT配置
    SECRET_KEY: str  # 用于JWT签名和配置加密
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 120  # 2小时
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7  # 7天
    JWT_ISSUER: str = "AI-miniSOC"
    JWT_AUDIENCE: str = "AI-miniSOC-Client"
    ACCESS_TOKEN_ATTEMPT_LIMIT: int = 5
    ACCESS_TOKEN_LOCKOUT_MINUTES: int = 30

    # 加密配置
    ENCRYPTION_KEY: str  # 用于敏感配置加密（Fernet）

    # 后端配置
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://localhost:3006",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3006",
        "http://192.168.0.42:5173",
        "http://192.168.0.128:5173"
    ]

    @field_validator('BACKEND_CORS_ORIGINS', mode='before')
    @classmethod
    def parse_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    # Wazuh配置
    WAZUH_API_URL: str = "https://192.168.0.40:55000"
    WAZUH_API_USERNAME: str
    WAZUH_API_PASSWORD: str

    # Webhook配置
    WAZUH_WEBHOOK_KEY: str = "change-this-in-production"
    WAZUH_WEBHOOK_ALLOWED_IPS: str = "192.168.0.30,192.168.0.40,127.0.0.1"

    @property
    def webhook_allowed_ips_list(self) -> list[str]:
        """解析Webhook允许的IP列表"""
        return [ip.strip() for ip in self.WAZUH_WEBHOOK_ALLOWED_IPS.split(",")]

    # Loki配置
    LOKI_API_URL: str = "http://192.168.0.30:3100"

    # 日志配置
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # 忽略.env中的额外配置项


# 创建全局配置实例
settings = Settings()
