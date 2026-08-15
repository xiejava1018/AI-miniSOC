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

    # OpenSearch 配置（Wazuh Indexer）
    OPENSEARCH_URL: str = "https://192.168.0.40:9200"
    OPENSEARCH_USER: str = "admin"
    OPENSEARCH_PASSWORD: str = ""

    # Webhook配置
    WAZUH_WEBHOOK_KEY: str = "change-this-in-production"
    WAZUH_WEBHOOK_ALLOWED_IPS: str = "192.168.0.30,192.168.0.40,127.0.0.1"

    @property
    def webhook_allowed_ips_list(self) -> list[str]:
        """解析Webhook允许的IP列表"""
        return [ip.strip() for ip in self.WAZUH_WEBHOOK_ALLOWED_IPS.split(",")]

    # Collector API Key 配置
    COLLECTOR_API_KEYS: str = ""  # 逗号分隔，如 sk-minisoc-tplink-xxx,sk-minisoc-wazuh-yyy

    @property
    def collector_api_keys_list(self) -> list[str]:
        """解析 Collector API Key 列表"""
        if not self.COLLECTOR_API_KEYS:
            return []
        return [k.strip() for k in self.COLLECTOR_API_KEYS.split(",")]

    # Loki配置
    LOKI_API_URL: str = "http://192.168.0.30:3100"

    # 上网行为异常检测配置（运行时规则阈值走 soc_system_config，此处仅进程级开关）
    BROWSING_DETECT_ENABLED: bool = True

    # 告警治理摘要自动调度（每日定时生成 + 通知推送；
    # 运行时阈值/噪声名单走 soc_system_config[alert_governance]）
    ALERT_DIGEST_SCHEDULER_ENABLED: bool = True
    ALERT_DIGEST_SCHEDULER_HOUR: int = 8  # 每日生成摘要的整点小时（0-23）

    # CISA KEV（在野利用威胁情报，T6 决策2：点亮 AI 评分 15% 权重）
    CISA_KEV_URL: str = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    CISA_KEV_SCHEDULER_ENABLED: bool = True  # 24h 自动同步（启动后首次延迟 120s）


    # 日志配置
    LOG_LEVEL: str = "INFO"

    # Claude Code CLI 配置（通过本地 claude 子进程调用）
    CLAUDE_CLI_PATH: str = "claude"  # 绝对路径或 PATH 中可执行
    CLAUDE_CLI_MODEL: str = "sonnet"  # 别名或完整 ID（claude-opus-4-8 等）
    CLAUDE_CLI_TIMEOUT: int = 300  # 单次生成超时（秒）
    CLAUDE_CLI_WORKSPACE: str = ""  # AI 工作目录（默认临时目录）
    CLAUDE_CLI_EFFORT: str = "medium"  # low|medium|high|xhigh|max
    CLAUDE_CLI_ALLOWED_TOOLS: str = ""  # 逗号分隔的工具白名单；空=默认
    CLAUDE_CLI_DANGEROUSLY_SKIP: bool = False  # 仅在隔离环境开启
    CLAUDE_CLI_NO_PERSIST: bool = True  # True=用 --no-session-persistence，CLI 不留本地 session

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"  # 忽略.env中的额外配置项


# 创建全局配置实例
settings = Settings()
