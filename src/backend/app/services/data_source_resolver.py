"""数据源解析器（DataSourceResolver）

设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §5.4.2 / §5.7

职责：
- 给定 source_type，返回当前生效的连接配置（dict）
- 优先级：DB 默认实例 → DB 任一启用实例 → settings.WAZUH_API_URL 等 → 失败回落 None
- 60s 进程内缓存（与既有 alert_governance_config / browsing_detection.config 一致）
- 任何异常一律吞掉并回落 settings，不得中断业务调用

注意：业务代码构造客户端时，**显式传入参数仍最高优先级**（保持向后兼容）。
本解析器只接管"没有显式传入时"的自动解析路径。
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.data_source import DataSource

logger = logging.getLogger(__name__)

_CACHE_TTL = 60  # 秒
_ORIGIN_NONE = "none"
_ORIGIN_ENV = "env"


@dataclass
class ResolvedConfig:
    config: Dict[str, Any]
    origin: str  # "db:<code>" | "env" | "none"
    source_code: Optional[str] = None


def _decrypt_or_none(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    try:
        return __import__(
            "app.services.encryption_service", fromlist=["encryption_service"]
        ).encryption_service.decrypt_if_needed(value)
    except Exception:
        return None


def _ds_to_config(ds: DataSource) -> Dict[str, Any]:
    cfg = {
        "endpoint": ds.endpoint,
        "auth_type": ds.auth_type,
        "username": ds.auth_username,
        "password": _decrypt_or_none(ds.auth_secret),
        "verify_ssl": ds.verify_ssl,
        "timeout_seconds": ds.timeout_seconds,
        "retry_times": ds.retry_times,
        "retry_backoff_seconds": ds.retry_backoff_seconds,
        "config_json": ds.config_json or {},
    }
    return cfg


def _fallback_from_env(source_type: str) -> Optional[Dict[str, Any]]:
    """从 settings.* 回落（无 DB 配置时）。"""
    if source_type == "wazuh":
        if getattr(settings, "WAZUH_API_URL", None):
            return {
                "endpoint": settings.WAZUH_API_URL,
                "auth_type": "basic",
                "username": getattr(settings, "WAZUH_API_USERNAME", None),
                "password": getattr(settings, "WAZUH_API_PASSWORD", None),
                "verify_ssl": False,
                "timeout_seconds": 30,
                "retry_times": 3,
                "retry_backoff_seconds": 2,
                "config_json": {},
            }
        return None
    if source_type == "opensearch":
        if getattr(settings, "OPENSEARCH_URL", None):
            return {
                "endpoint": settings.OPENSEARCH_URL,
                "auth_type": (
                    "basic"
                    if getattr(settings, "OPENSEARCH_USER", None)
                    or getattr(settings, "OPENSEARCH_PASSWORD", None)
                    else "none"
                ),
                "username": getattr(settings, "OPENSEARCH_USER", None),
                "password": getattr(settings, "OPENSEARCH_PASSWORD", None),
                "verify_ssl": False,
                "timeout_seconds": 30,
                "retry_times": 3,
                "retry_backoff_seconds": 2,
                "config_json": {},
            }
        return None
    if source_type == "loki":
        if getattr(settings, "LOKI_API_URL", None):
            return {
                "endpoint": settings.LOKI_API_URL,
                "auth_type": "none",
                "username": None,
                "password": None,
                "verify_ssl": False,
                "timeout_seconds": 30,
                "retry_times": 3,
                "retry_backoff_seconds": 2,
                "config_json": {},
            }
        return None
    return None


class DataSourceResolver:
    """进程级单例（线程安全）。"""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: Dict[str, ResolvedConfig] = {}
        self._cached_at: Dict[str, float] = {}

    def _now(self) -> float:
        return time.time()

    def _is_fresh(self, key: str) -> bool:
        ts = self._cached_at.get(key)
        return ts is not None and (self._now() - ts) < _CACHE_TTL

    def invalidate(self, source_type: Optional[str] = None) -> None:
        with self._lock:
            if source_type is None:
                self._cache.clear()
                self._cached_at.clear()
            else:
                self._cache.pop(source_type, None)
                self._cached_at.pop(source_type, None)

    def resolve(self, source_type: str, db: Optional[Session] = None) -> ResolvedConfig:
        """返回 ResolvedConfig。db 可空（无 DB 时直接回落 env）。"""
        with self._lock:
            if self._is_fresh(source_type):
                return self._cache[source_type]

        resolved = self._resolve_uncached(source_type, db)
        with self._lock:
            self._cache[source_type] = resolved
            self._cached_at[source_type] = self._now()
        return resolved

    def _resolve_uncached(
        self, source_type: str, db: Optional[Session]
    ) -> ResolvedConfig:
        """优先级：DB 默认 → DB 任一启用 → env → none。"""
        # 1) DB
        if db is not None:
            try:
                # 1a) 默认实例
                ds = (
                    db.query(DataSource)
                    .filter(
                        DataSource.source_type == source_type,
                        DataSource.enabled.is_(True),
                        DataSource.is_default.is_(True),
                    )
                    .first()
                )
                if ds:
                    return ResolvedConfig(
                        config=_ds_to_config(ds),
                        origin=f"db:{ds.source_code}",
                        source_code=ds.source_code,
                    )
                # 1b) 任一启用实例
                ds = (
                    db.query(DataSource)
                    .filter(
                        DataSource.source_type == source_type,
                        DataSource.enabled.is_(True),
                    )
                    .first()
                )
                if ds:
                    logger.warning(
                        "data source %s 未设默认实例，使用 %s；建议在界面指定默认",
                        source_type,
                        ds.source_code,
                    )
                    return ResolvedConfig(
                        config=_ds_to_config(ds),
                        origin=f"db:{ds.source_code}",
                        source_code=ds.source_code,
                    )
            except Exception as e:
                logger.warning(
                    "resolver 读 DB 失败（fallback env）：type=%s err=%s",
                    source_type,
                    e,
                )

        # 2) env
        env_cfg = _fallback_from_env(source_type)
        if env_cfg:
            return ResolvedConfig(
                config=env_cfg, origin=_ORIGIN_ENV, source_code=None
            )

        # 3) 无
        return ResolvedConfig(config={}, origin=_ORIGIN_NONE, source_code=None)

    def resolve_status(self, db: Session) -> Dict[str, ResolvedConfig]:
        """返回各 source_type 的当前生效来源（用于界面提示）。"""
        types = ["wazuh", "opensearch", "loki", "tplink", "scanner"]
        result: Dict[str, ResolvedConfig] = {}
        for t in types:
            result[t] = self.resolve(t, db)
        return result


def get_endpoint(source_type: str) -> Optional[str]:
    """便捷函数：开短会话读 endpoint（适用于无 db 入参的调用点，如 MCP tool / 单次探活）。

    60s 进程内缓存意味着频繁调用不会打 DB。遇异常返回 None（调用方需自行处理）。
    """
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        return data_source_resolver.resolve(source_type, db).config.get("endpoint")
    except Exception:
        return None
    finally:
        db.close()


def get_config(source_type: str) -> Dict[str, Any]:
    """便捷函数：开短会话读完整 config dict。同 get_endpoint 适用场景。"""
    from app.core.database import SessionLocal
    db = SessionLocal()
    try:
        return data_source_resolver.resolve(source_type, db).config or {}
    except Exception:
        return {}
    finally:
        db.close()


data_source_resolver = DataSourceResolver()