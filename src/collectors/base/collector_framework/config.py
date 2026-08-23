"""
Collector 配置管理

支持 YAML 配置文件 + 环境变量覆盖（环境变量优先级更高）。
"""

from dataclasses import dataclass, field
from typing import Optional
import os
import re

import yaml

# 形如 ${VAR} / ${VAR:-default} 的未展开占位符
PLACEHOLDER_RE = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*(:-[^}]*)?\}$")


def resolve(env_key: str, yaml_value=None, default=None, *, field_name: str = ""):
    """环境变量优先、YAML 其次、最后 default 地解析一个配置项。

    为什么需要它：yaml.safe_load **不会**展开 ${VAR}。仓库里的 config.yaml
    写的是 `user: ${WAZUH_USER:-wazuh}` 这种占位符（故意不入库明文密码），
    直接 `wazuh_cfg.get("user")` 拿到的是字面量字符串 "${WAZUH_USER:-wazuh}"，
    拿它去认证就是 401。生产真出过（2026-08-23）。

    占位符没被环境变量覆盖时，**宁可启动失败也不拿它发请求**——
    捕到一个启动期的 ValueError 比在日志里看一万次 401 容易得多。
    """
    env_val = os.getenv(env_key)
    if env_val not in (None, ""):
        return env_val

    if isinstance(yaml_value, str) and PLACEHOLDER_RE.match(yaml_value.strip()):
        # YAML 里是占位符但环变量缺失 → 当作未配置
        if default is not None:
            return default
        raise ValueError(
            f"配置项 {field_name or env_key} 在 YAML 里是未展开的占位符 "
            f"{yaml_value!r}，且环境变量 {env_key} 未设置。"
            f"请在 src/collectors/.env 里补上 {env_key}。"
        )

    if yaml_value not in (None, ""):
        return yaml_value
    return default


@dataclass
class CollectorConfig:
    """Collector 通用配置"""

    # AI-miniSOC 连接
    minisoc_url: str = ""
    minisoc_api_key: str = ""

    # 采集调度
    interval: int = 300
    collect_types: Optional[list[str]] = None

    # 运行模式
    once: bool = False

    # 数据源特定配置（由各 Collector 自行解析）
    extra: dict = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str) -> "CollectorConfig":
        with open(path) as f:
            cfg = yaml.safe_load(f) or {}

        minisoc_cfg = cfg.get("minisoc", {})
        collect_cfg = cfg.get("collect", {})

        return cls(
            minisoc_url=resolve(
                "MINISOC_URL", minisoc_cfg.get("url"), "", field_name="minisoc.url"
            ),
            minisoc_api_key=resolve(
                "MINISOC_API_KEY",
                minisoc_cfg.get("api_key"),
                "",
                field_name="minisoc.api_key",
            ),
            interval=int(os.getenv("COLLECT_INTERVAL", collect_cfg.get("interval", 300))),
            collect_types=collect_cfg.get("types"),
            once=collect_cfg.get("once", False),
            extra=cfg,
        )
