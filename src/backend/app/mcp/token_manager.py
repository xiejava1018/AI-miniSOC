"""
MCP Token Manager — 自动维护 JWT，避免 Agent 长期持有过期 token。

工作流程：
1. 启动时用账号密码登录一次，拿 access + refresh。
2. 后台线程在 access 过期前 N 分钟（默认 5）自动用 refresh 换新 token。
3. 提供 `get_token()` 同步接口供 MCP tool 调用，每次返回当前有效 token。
4. refresh 也失败（账号被锁/密码改/refresh 撤销）时进入 `expired` 状态，
   调用方收到 `TokenExpiredError`，需要重新配置账号密码。

设计要点：
- 线程安全：用 `threading.RLock` 保护 token dict
- 单例：全局共用一个 manager，多个 MCP tool 共享
- 进程内 in-memory：单进程足够，多实例需切 Redis（TODO）
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

# 任务可观测性心跳（v0.4.2 Phase 2.1）
# 线程型任务：每 tick 上报 heartbeat，真正 refresh 时写 run
from app.services.task_observability.heartbeat import ThreadHeartbeat

_TASK_HEARTBEAT = ThreadHeartbeat(
    task_key="mcp_token_refresher",
    task_name="MCP Token 刷新",
    owner_module="app.mcp.token_manager",
    interval_s=60,
    timeout_s=300,
)


class TokenExpiredError(RuntimeError):
    """账号凭证彻底失效，需要人工重新登录（MCP 配置更新）"""


@dataclass
class TokenBundle:
    """一组 access + refresh"""
    access_token: str
    refresh_token: str
    expires_at: float  # access 过期时间（Unix 秒）
    refresh_expires_at: float  # refresh 过期时间
    username: str = ""

    @property
    def access_valid(self) -> bool:
        return time.time() < self.expires_at

    @property
    def refresh_valid(self) -> bool:
        return time.time() < self.refresh_expires_at


class TokenManager:
    """单例 Token 管理器：自动刷新 + 线程安全"""

    _instance: Optional["TokenManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._bundle: Optional[TokenBundle] = None
        self._credentials: Optional[tuple[str, str]] = None  # (username, password)
        self._refresh_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        # refresh 比 access 提前这么多秒触发（避免边界 race）
        self._refresh_margin_seconds = 300  # 5 分钟

    # ------------------------------------------------------------------ 单例
    @classmethod
    def get_instance(cls) -> "TokenManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------ 配置
    def configure(self, username: str, password: str, api_base: Optional[str] = None) -> TokenBundle:
        """
        配置账号密码 + 立即登录拿 token。后续会自动后台刷新。

        Returns:
            当前生效的 TokenBundle
        """
        with self._lock:
            self._credentials = (username, password)
            self._api_base = api_base or f"http://localhost:{settings.BACKEND_PORT}/api/v1"

            # 立即登录一次
            bundle = self._do_login(username, password)
            self._bundle = bundle
            logger.info(
                "TokenManager configured for user=%s, access expires at %s",
                username,
                datetime.fromtimestamp(bundle.expires_at, tz=timezone.utc).isoformat(),
            )

            # 启动后台刷新线程（首次）
            self._start_refresh_thread()
            return bundle

    # ------------------------------------------------------------------ 查询
    def get_token(self) -> str:
        """
        同步返回当前有效的 access token。

        Raises:
            TokenExpiredError: 凭证彻底失效，需要重新 configure()
        """
        with self._lock:
            if self._bundle is None:
                raise TokenExpiredError("TokenManager 未配置，请先调用 configure()")
            # 同步兜底：如果即将过期但后台线程没来得及刷，同步刷一次
            if not self._bundle.access_valid:
                if self._bundle.refresh_valid:
                    logger.info("access 已过期，触发同步 refresh")
                    self._refresh_now()
                else:
                    raise TokenExpiredError(
                        f"refresh token 已过期（user={self._bundle.username}），需要重新登录"
                    )
            if self._bundle is None or not self._bundle.access_valid:
                raise TokenExpiredError("Token 刷新失败")
            return self._bundle.access_token

    def get_refresh_token(self) -> str:
        with self._lock:
            if self._bundle is None:
                raise TokenExpiredError("TokenManager 未配置")
            return self._bundle.refresh_token

    def status(self) -> dict:
        """查询当前 token 状态（供 MCP debug tool 用）"""
        with self._lock:
            if not self._bundle:
                return {"configured": False}
            now = time.time()
            return {
                "configured": True,
                "username": self._bundle.username,
                "access_valid": self._bundle.access_valid,
                "access_expires_in_seconds": max(0, int(self._bundle.expires_at - now)),
                "refresh_valid": self._bundle.refresh_valid,
                "refresh_expires_in_seconds": max(0, int(self._bundle.refresh_expires_at - now)),
            }

    # ------------------------------------------------------------------ 登录/刷新
    def _do_login(self, username: str, password: str) -> TokenBundle:
        """调 /auth/login 拿新 token"""
        import httpx  # 延迟导入，避免循环
        with httpx.Client(timeout=10) as client:
            r = client.post(
                f"{self._api_base}/auth/login",
                json={"username": username, "password": password},
            )
            r.raise_for_status()
            data = r.json()
            # 项目用 {code, msg, data} 响应包装
            body = data.get("data", data)
            access = body["access_token"]
            refresh = body["refresh_token"]
            expires_in = body["expires_in"]  # 秒
            now = time.time()
            return TokenBundle(
                access_token=access,
                refresh_token=refresh,
                expires_at=now + expires_in,
                # refresh 7 天（settings.REFRESH_TOKEN_EXPIRE_DAYS）
                refresh_expires_at=now + settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
                username=username,
            )

    def _refresh_now(self) -> None:
        """用 refresh token 换新 access + refresh（轮换）"""
        import httpx
        if not self._bundle or not self._credentials:
            raise TokenExpiredError("TokenManager 未配置")
        with httpx.Client(timeout=10) as client:
            r = client.post(
                f"{self._api_base}/auth/refresh",
                json={"refresh_token": self._bundle.refresh_token},
            )
            if r.status_code != 200:
                # refresh 失败 → 重新登录（用最初凭证）
                logger.warning(
                    "refresh 失败（status=%s body=%s），尝试重新登录",
                    r.status_code,
                    r.text[:200],
                )
                username, password = self._credentials
                self._bundle = self._do_login(username, password)
                return
            data = r.json().get("data", r.json())
            now = time.time()
            self._bundle = TokenBundle(
                access_token=data["access_token"],
                refresh_token=data["refresh_token"],
                expires_at=now + data["expires_in"],
                refresh_expires_at=self._bundle.refresh_expires_at,  # 沿用原 refresh 过期
                username=self._bundle.username,
            )
            logger.info(
                "Token 已自动刷新，user=%s, 新 access 过期时间=%s",
                self._bundle.username,
                datetime.fromtimestamp(self._bundle.expires_at, tz=timezone.utc).isoformat(),
            )

    # ------------------------------------------------------------------ 后台线程
    def _start_refresh_thread(self) -> None:
        if self._refresh_thread and self._refresh_thread.is_alive():
            return
        self._stop_event.clear()
        # 注册到任务可观测性（task_type=thread）
        try:
            _TASK_HEARTBEAT.register()
        except Exception:
            logger.debug("heartbeat register failed", exc_info=True)
        t = threading.Thread(
            target=self._refresh_loop,
            name="mcp-token-refresher",
            daemon=True,
        )
        self._refresh_thread = t
        t.start()

    def _refresh_loop(self) -> None:
        """每 60s 检查一次，临近过期则刷新"""
        while not self._stop_event.is_set():
            try:
                # 每 tick 上报心跳（不写 run 表，避免一天 1440 条空记录）
                _TASK_HEARTBEAT.tick(
                    stats={
                        "configured": self._bundle is not None,
                        "access_valid": bool(self._bundle and self._bundle.access_valid),
                        "refresh_valid": bool(self._bundle and self._bundle.refresh_valid),
                    }
                )
                with self._lock:
                    if self._bundle and self._bundle.access_valid:
                        remaining = self._bundle.expires_at - time.time()
                        if remaining <= self._refresh_margin_seconds and self._bundle.refresh_valid:
                            logger.info("即将过期（剩余 %.0fs），触发后台 refresh", remaining)
                            _TASK_HEARTBEAT.run_started(trigger="scheduled")
                            try:
                                self._refresh_now()
                                _TASK_HEARTBEAT.run_succeeded(
                                    stats={"remaining_s": int(remaining)},
                                    trigger="scheduled",
                                )
                            except TokenExpiredError as e:
                                _TASK_HEARTBEAT.run_failed(
                                    e,
                                    stats={"remaining_s": int(remaining), "fatal": True},
                                    trigger="scheduled",
                                )
                                raise
                            except Exception as e:
                                _TASK_HEARTBEAT.run_failed(
                                    e,
                                    stats={"remaining_s": int(remaining)},
                                    trigger="scheduled",
                                )
                                raise
            except TokenExpiredError:
                logger.error("后台 refresh 线程终止：凭证失效")
                return
            except Exception as e:  # noqa: BLE001
                logger.exception("后台 refresh 出错: %s", e)
            self._stop_event.wait(60)  # 每分钟检查一次

    def shutdown(self) -> None:
        """停止后台线程（应用关闭时调用）"""
        self._stop_event.set()
        try:
            _TASK_HEARTBEAT.unregister()
        except Exception:
            logger.debug("heartbeat unregister failed", exc_info=True)


# 全局便捷访问
def get_token_manager() -> TokenManager:
    return TokenManager.get_instance()