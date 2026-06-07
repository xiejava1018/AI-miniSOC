"""
Collector 配置管理

支持 YAML 配置文件 + 环境变量覆盖（环境变量优先级更高）。
"""

from dataclasses import dataclass, field
from typing import Optional
import os

import yaml


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
            minisoc_url=os.getenv("MINISOC_URL", minisoc_cfg.get("url", "")),
            minisoc_api_key=os.getenv("MINISOC_API_KEY", minisoc_cfg.get("api_key", "")),
            interval=int(os.getenv("COLLECT_INTERVAL", collect_cfg.get("interval", 300))),
            collect_types=collect_cfg.get("types"),
            once=collect_cfg.get("once", False),
            extra=cfg,
        )
