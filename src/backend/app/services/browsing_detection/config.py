"""
检测配置管理

从 soc_system_config 表读取 category='browsing_detection' 的配置，
带 60 秒缓存，配置变更后下个周期自动生效。
"""

import logging
import time
from dataclasses import dataclass, field
from typing import List

from sqlalchemy.orm import Session

from app.models.system_config import SystemConfig

logger = logging.getLogger(__name__)

CONFIG_CATEGORY = "browsing_detection"
_CACHE_TTL = 60  # 配置缓存 60 秒

# 默认配置（与设计文档 §7 一致）
_DEFAULTS = {
    "enabled": ("true", "bool"),
    "interval_seconds": ("300", "int"),
    "window_minutes": ("5", "int"),
    "score_threshold": ("50", "int"),
    "severity_high": ("80", "int"),
    "severity_critical": ("100", "int"),
    "burst_threshold": ("30", "int"),
    "night_start_hour": ("2", "int"),
    "night_end_hour": ("5", "int"),
    "night_count_threshold": ("5", "int"),
    "tunnel_keywords": ("easytier|stun|frp|fatedier|zerotier|tailscale|n2n|wireguard|tinc|nebula", "str"),
    "blacklist_domains": ("", "str"),
    "whitelist_domains": ("", "str"),
    "whitelist_ips": ("", "str"),
    "suppress_minutes": ("30", "int"),
    "notify_user_ids": ("", "str"),
    "baseline_days": ("7", "int"),
    "rules_enabled": ("R1,R2,R3,R4,R5,R6", "str"),
}


def _coerce(value: str, value_type: str):
    if value_type == "bool":
        return str(value).strip().lower() in ("true", "1", "yes", "on")
    if value_type == "int":
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    return str(value) if value is not None else ""


@dataclass
class DetectionConfig:
    """检测配置（强类型）"""

    enabled: bool = True
    interval_seconds: int = 300
    window_minutes: int = 5
    score_threshold: int = 50
    severity_high: int = 80
    severity_critical: int = 100
    burst_threshold: int = 30
    night_start_hour: int = 2
    night_end_hour: int = 5
    night_count_threshold: int = 5
    tunnel_keywords: str = ""
    blacklist_domains: str = ""
    whitelist_domains: str = ""
    whitelist_ips: str = ""
    suppress_minutes: int = 30
    notify_user_ids: str = ""
    baseline_days: int = 7
    rules_enabled: str = "R1,R2,R3,R4,R5,R6"

    # 便捷派生属性 -------------------------------------------------

    @property
    def rules_enabled_set(self) -> set:
        return {r.strip().upper() for r in self.rules_enabled.split(",") if r.strip()}

    @property
    def whitelist_domain_set(self) -> set:
        return {d.strip().lower() for d in self.whitelist_domains.split(",") if d.strip()}

    @property
    def whitelist_ip_set(self) -> set:
        return {ip.strip() for ip in self.whitelist_ips.split(",") if ip.strip()}

    @property
    def config_blacklist_set(self) -> set:
        return {d.strip().lower() for d in self.blacklist_domains.split(",") if d.strip()}

    @property
    def notify_user_id_list(self) -> List[int]:
        ids = []
        for s in self.notify_user_ids.split(","):
            s = s.strip()
            if s:
                try:
                    ids.append(int(s))
                except ValueError:
                    pass
        return ids

    def severity_for(self, score: int) -> str:
        """按分值映射严重等级"""
        if score >= self.severity_critical:
            return "critical"
        if score >= self.severity_high:
            return "high"
        if score >= self.score_threshold:
            return "medium"
        return "low"


class ConfigCache:
    """配置缓存（单进程）"""

    def __init__(self) -> None:
        self._config: DetectionConfig | None = None
        self._loaded_at: float = 0.0

    def get(self, db: Session) -> DetectionConfig:
        """获取配置，命中缓存则直接返回"""
        now = time.time()
        if self._config is not None and (now - self._loaded_at) < _CACHE_TTL:
            return self._config

        # 从 DB 读取
        rows = (
            db.query(SystemConfig)
            .filter(SystemConfig.category == CONFIG_CATEGORY)
            .all()
        )
        db_map = {r.key: (r.value, r.value_type or "str") for r in rows}

        kwargs = {}
        for key, (default_val, vtype) in _DEFAULTS.items():
            raw_val, vt = db_map.get(key, (default_val, vtype))
            kwargs[key] = _coerce(raw_val, vt)

        self._config = DetectionConfig(**kwargs)
        self._loaded_at = now
        logger.debug("检测配置已加载: enabled=%s interval=%ss", self._config.enabled, self._config.interval_seconds)
        return self._config

    def invalidate(self) -> None:
        """使缓存失效（配置变更时调用）"""
        self._config = None
        self._loaded_at = 0.0


# 全局缓存实例
config_cache = ConfigCache()


def get_detection_config(db: Session) -> DetectionConfig:
    """获取检测配置的便捷入口"""
    return config_cache.get(db)
