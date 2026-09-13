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
    if source_type == "ai":
        # AI Provider 回落：GLM_* 环境变量（OpenAI 兼容协议）
        if getattr(settings, "GLM_API_KEY", None):
            return {
                "endpoint": getattr(settings, "GLM_API_BASE", "https://open.bigmodel.cn/api/paas/v4/"),
                "auth_type": "apikey",
                "username": None,
                "password": settings.GLM_API_KEY,
                "verify_ssl": False,
                "timeout_seconds": 60,
                "retry_times": 2,
                "retry_backoff_seconds": 2,
                "config_json": {"model": getattr(settings, "GLM_MODEL", "glm-4-flash"), "protocol": "openai"},
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

    def resolve_ai(self, scene: Optional[str] = None, db: Optional[Session] = None) -> ResolvedConfig:
        """AI Provider 场景路由（多模型核心）：

        优先级：
        1. config_json.scenes 含 scene 的启用 ai 实例（精确路由，如报告用 deepseek）
        2. is_default=true 的启用 ai 实例
        3. 任一启用 ai 实例（WARN）
        4. env 回落 GLM_*（origin="env"，现行为不变）

        scene=None 表示不路由，直接取默认。场景例：asset_query/report/impact/
        chat/compliance/knowledge/risk/reconcile/behavior
        """
        cache_key = f"ai:{scene or '*'}"
        with self._lock:
            if self._is_fresh(cache_key):
                return self._cache[cache_key]

        resolved = self._resolve_ai_uncached(scene, db)
        with self._lock:
            self._cache[cache_key] = resolved
            self._cached_at[cache_key] = self._now()
        return resolved

    def _resolve_ai_uncached(
        self, scene: Optional[str], db: Optional[Session]
    ) -> ResolvedConfig:
        """查 soc_ai_providers（AI 配置独立表，2026-09-13 拆分）。"""
        if db is not None:
            try:
                from app.models.ai_provider import AIProvider

                rows = (
                    db.query(AIProvider)
                    .filter(AIProvider.enabled.is_(True))
                    .all()
                )
                if rows:
                    # 1) 精确场景路由
                    for p in rows:
                        if scene and scene in (p.scenes or []):
                            return self._ai_provider_to_config(p)
                    # 2) 默认实例
                    for p in rows:
                        if p.is_default:
                            return self._ai_provider_to_config(p)
                    # 3) 任一启用
                    logger.warning(
                        "ai provider 未设默认且场景 %s 无精确路由，使用 %s",
                        scene,
                        rows[0].provider_code,
                    )
                    return self._ai_provider_to_config(rows[0])
            except Exception as e:
                logger.warning("resolve_ai 读 DB 失败（fallback env）：err=%s", e)
        return self.resolve("ai", db)

    @staticmethod
    def _ai_provider_to_config(p) -> ResolvedConfig:
        cfg = {
            "endpoint": p.base_url,
            "auth_type": "apikey",
            "username": None,
            "password": _decrypt_or_none(p.api_key),
            "verify_ssl": False,
            "timeout_seconds": p.timeout_seconds,
            "retry_times": 2,
            "retry_backoff_seconds": 2,
            "config_json": {
                "model": p.model_name,
                "protocol": p.protocol,
                "scenes": p.scenes or [],
                "max_tokens": p.max_tokens,
            },
        }
        return ResolvedConfig(
            config=cfg, origin=f"db:{p.provider_code}", source_code=p.provider_code
        )

    def invalidate_ai(self) -> None:
        """AI 配置变更后清场景路由缓存（键为 ai:*）。"""
        with self._lock:
            for k in [k for k in self._cache if k.startswith("ai:")]:
                self._cache.pop(k, None)
                self._cached_at.pop(k, None)


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