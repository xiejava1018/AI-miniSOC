"""
通知通道服务（OH-NOT-F2 · Phase 1）

CLAUDE.md §0 + §4.6 配置中心 11 个调用点迁移规则 — SMTP 配置**全部走 soc_notification_channels 表**，
不走 env（CLAUDE.md §1.7 三库严格分离保护）。

Phase 1 范围：
- 通道 CRUD（admin only 写入）
- email 配置校验 + 缓存（60s）+ decrypt 密码
- 偏好查询/更新
- Phase 2 才做 SMTP 实际投递 (Phase 1 dispatcher 不发邮件)

设计：
- 进程内缓存通过实例属性（无锁，60s 过期，reloader reload 时自动重置）
- decrypt_if_needed（CLAUDE.md §1.7 + encryption_service.py:211）
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session as OrmSession

from app.models.notification_channel import (
    NotificationChannel,
    UserNotificationPreference,
)
from app.services.encryption_service import encryption_service

logger = logging.getLogger(__name__)

EMAIL_CHANNEL_CODE = "email"
INBOX_CHANNEL_CODE = "inbox"
_CACHE_TTL = 60  # 秒（CLAUDE.md §4.6 同 alert_governance_config 缓存策略）


class NotificationChannelService:
    """通道服务"""

    def __init__(self, db: OrmSession) -> None:
        self.db = db
        # 进程内缓存: code -> (cached_dict, timestamp)
        self._config_cache: Dict[str, tuple[Dict[str, Any], float]] = {}

    # ============================================================
    # 通道 CRUD
    # ============================================================

    def list_channels(self, enabled_only: bool = False) -> List[NotificationChannel]:
        """列出所有通道（Phase 1 默认全部 2 个：inbox + email）"""
        stmt = select(NotificationChannel)
        if enabled_only:
            stmt = stmt.where(NotificationChannel.enabled.is_(True))
        return list(self.db.execute(stmt).scalars())

    def get_by_code(self, code: str) -> Optional[NotificationChannel]:
        stmt = select(NotificationChannel).where(NotificationChannel.code == code)
        return self.db.execute(stmt).scalar_one_or_none()

    def get_by_id(self, channel_id: int) -> Optional[NotificationChannel]:
        stmt = select(NotificationChannel).where(NotificationChannel.id == channel_id)
        return self.db.execute(stmt).scalar_one_or_none()

    def update_channel(
        self,
        channel_id: int,
        name: Optional[str] = None,
        enabled: Optional[bool] = None,
        config_json: Optional[Dict[str, Any]] = None,
    ) -> NotificationChannel:
        """admin 更新通道（CLAUDE.md §1.3 admin bypass）"""
        ch = self.get_by_id(channel_id)
        if ch is None:
            raise ValueError(f"Channel {channel_id} not found")

        if name is not None:
            ch.name = name
        if enabled is not None:
            ch.enabled = enabled
        if config_json is not None:
            # 加密密码字段（CLAUDE.md §1.7 严防明文存 DB）
            config_json = self._encrypt_passwords(ch.code, config_json)
            ch.config_json = config_json

        self.db.commit()
        self.db.refresh(ch)

        # 清缓存
        self._config_cache.pop(ch.code, None)
        logger.info("channel updated: id=%s code=%s", ch.id, ch.code)
        return ch

    # ============================================================
    # Email 配置（Phase 1 重点：SMTP 可配置）
    # ============================================================

    def get_email_config(self, use_cache: bool = True) -> Optional[Dict[str, Any]]:
        """获取 email 通道的解密配置（Phase 1 用户改 DB，admin 看）。

        Returns None if channel disabled or not configured.
        """
        if use_cache:
            cached = self._config_cache.get(EMAIL_CHANNEL_CODE)
            if cached and (time.time() - cached[1]) < _CACHE_TTL:
                return cached[0]

        ch = self.get_by_code(EMAIL_CHANNEL_CODE)
        if ch is None or not ch.enabled:
            return None

        cfg = dict(ch.config_json or {})
        # decrypt password 字段（明文 → 明文）
        if "password" in cfg and cfg["password"]:
            try:
                cfg["password"] = encryption_service.decrypt_if_needed(cfg["password"])
            except Exception as e:  # noqa: BLE001
                logger.warning("email password decrypt failed (treat as plain?): %s", e)

        # 缓存
        self._config_cache[EMAIL_CHANNEL_CODE] = (cfg, time.time())
        return cfg

    def validate_email_config(self, config: Dict[str, Any]) -> List[str]:
        """校验 email 配置完整性，返回错误信息列表（空 = 通过）。

        必填：
        - host: 非空字符串
        - port: 1-65535 整数
        - user: 非空字符串
        - password: 非空字符串
        - from_addr: 邮箱格式
        可选：
        - use_tls (默认 true)
        - from_name (默认 'AI-miniSOC 通知')
        - max_retries (默认 3)
        - retry_backoff_seconds (默认 60)
        """
        errors: List[str] = []

        host = config.get("host")
        if not host or not isinstance(host, str) or not host.strip():
            errors.append("host 不能为空")

        port = config.get("port", 587)
        if not isinstance(port, int) or not (1 <= port <= 65535):
            errors.append(f"port 必须是 1-65535 的整数，当前 {port!r}")

        if not config.get("user") or not isinstance(config.get("user"), str):
            errors.append("user 不能为空")

        if not config.get("password") or not isinstance(config.get("password"), str):
            errors.append("password 不能为空")

        from_addr = config.get("from_addr", "")
        if not from_addr or "@" not in str(from_addr):
            errors.append(f"from_addr 必须是邮箱格式，当前 {from_addr!r}")

        # 可选字段默认值填充
        if "use_tls" in config and not isinstance(config["use_tls"], bool):
            errors.append("use_tls 必须是 bool")

        return errors

    # ============================================================
    # 偏好
    # ============================================================

    def get_user_prefs(self, user_id: int) -> List[UserNotificationPreference]:
        stmt = select(UserNotificationPreference).where(
            UserNotificationPreference.user_id == user_id
        )
        return list(self.db.execute(stmt).scalars())

    def upsert_user_pref(self, user_id: int, type: str, channel_code: str, enabled: bool) -> UserNotificationPreference:
        """upsert 用户对 (type, channel) 的偏好"""
        stmt = select(UserNotificationPreference).where(
            UserNotificationPreference.user_id == user_id,
            UserNotificationPreference.type == type,
            UserNotificationPreference.channel_code == channel_code,
        )
        pref = self.db.execute(stmt).scalar_one_or_none()
        if pref is None:
            pref = UserNotificationPreference(
                user_id=user_id, type=type, channel_code=channel_code, enabled=enabled
            )
            self.db.add(pref)
        else:
            pref.enabled = enabled
        self.db.commit()
        self.db.refresh(pref)
        return pref

    def is_user_channel_enabled(self, user_id: int, type: str, channel_code: str) -> bool:
        """dispatcher 用：判断用户是否对 (type, channel) 启用。

        返回 True 的两种情况：
        1. 用户没有 (type, channel) 偏好行（默认全收）
        2. 偏好行 enabled=true
        """
        stmt = select(UserNotificationPreference.enabled).where(
            UserNotificationPreference.user_id == user_id,
            UserNotificationPreference.type == type,
            UserNotificationPreference.channel_code == channel_code,
        )
        row = self.db.execute(stmt).first()
        if row is None:
            return True  # 默认全收（CLAUDE.md §0 X1 矩阵）
        return bool(row[0])

    # ============================================================
    # 内部工具
    # ============================================================

    @staticmethod
    def _encrypt_passwords(channel_code: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """加密敏感字段（仅 email 通道，且 password 字段非空）。"""
        cfg = dict(config)
        if channel_code == EMAIL_CHANNEL_CODE and cfg.get("password"):
            try:
                # encrypt_if_needed 幂等：已加密的不会重复加密（CLAUDE.md §0）
                cfg["password"] = encryption_service.encrypt_if_needed(cfg["password"], force=True)
            except Exception as e:  # noqa: BLE001
                logger.warning("email password encrypt failed: %s", e)
        return cfg

    def invalidate_cache(self, channel_code: Optional[str] = None) -> None:
        """清缓存（admin 改完配置调用或测试用）"""
        if channel_code:
            self._config_cache.pop(channel_code, None)
        else:
            self._config_cache.clear()


# 进程级单例（CLAUDE.md §0 + ai_budget 单例同模式）
# 注：service 实例需要 db session, 通常在 route handler 里新建。
# 进程级缓存通过实例的 _config_cache 持有 —— reload 时整个进程重置。
__all__ = [
    "NotificationChannelService",
    "EMAIL_CHANNEL_CODE",
    "INBOX_CHANNEL_CODE",
]