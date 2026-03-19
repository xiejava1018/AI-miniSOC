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

    # 数据库连接字符串
    @property
    def DATABASE_URL(self) -> str:
        # 对密码进行 URL 编码，处理特殊字符
        encoded_password = quote_plus(self.DB_PASSWORD)
        return f"postgresql://{self.DB_USER}:{encoded_password}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # 智谱AI配置
    GLM_API_KEY: str
    GLM_MODEL: str = "glm-4-flash"
    GLM_API_BASE: str = "https://open.bigmodel.cn/api/paas/v4/"

    # JWT配置
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440

    # 后端配置
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    BACKEND_CORS_ORIGINS: Union[str, List[str]] = [
        "http://localhost:5173",
        "http://192.168.0.42:5173"
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

    # Loki配置
    LOKI_API_URL: str = "http://192.168.0.30:3100"

    # 日志配置
    LOG_LEVEL: str = "INFO"

    class Config:
        env_file = ".env"
        case_sensitive = True


# 创建全局配置实例
settings = Settings()
