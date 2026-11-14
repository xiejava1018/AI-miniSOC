"""ARL-Next 外部画像客户端（OH-ARL.5，design §6.2 告警富化实时只读查）。

用途：告警簇 AI 研判时补充「暴露面、开放端口、已验证漏洞、证书」上下文，
**不落库**（与 arl-collector 的落库通道互补）。

契约（design §2.1/§2.4 实测）：
  - 端点 GET /api/mcp/asset_profile?target=<IP或域名>，Header Token: <token>
  - **非 envelope 响应**：顶层直接是画像字段（与归档态端点的 {code,...} 不同，
    解析需分支——2026-11-14 端到端实测）
  - ARL 侧 120/min 配额；本地缓存 TTL（默认 300s）+ 熔断保护

诚实降级（C7）：未配置 / 熔断打开 / 超时 / 错误 → 返回 available=False 的
dict（带 reason），**绝不静默当作「无风险」**；研判链路继续走本地画像。
"""

from __future__ import annotations

import logging
import time

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_FAIL_THRESHOLD = 3      # 连续失败 N 次 → 熔断 open
_COOLDOWN_S = 60         # open 冷却后半开（试一次）
_PORTS_TOP = 10          # prompt 摘要上限（控 token）
_VULNS_TOP = 5


class ARLProfileClient:
    """ARL 外部画像客户端：缓存 + 熔断 + 诚实降级。"""

    def __init__(self):
        self._cache: dict[str, tuple[float, dict]] = {}
        self._consec_fail = 0
        self._open_since: float | None = None

    # ── 熔断状态 ──────────────────────────────────────
    def _circuit_open(self) -> bool:
        if self._open_since is None:
            return False
        if time.monotonic() - self._open_since >= _COOLDOWN_S:
            # 半开：放一次请求试探（本次失败会重新 open）
            return False
        return True

    def _record_success(self) -> None:
        self._consec_fail = 0
        self._open_since = None

    def _record_failure(self) -> None:
        self._consec_fail += 1
        if self._consec_fail >= _FAIL_THRESHOLD:
            self._open_since = time.monotonic()
            logger.warning(
                "ARL 外部画像熔断打开（连续失败 %d 次，冷却 %ds）",
                self._consec_fail, _COOLDOWN_S,
            )

    # ── 公开入口 ──────────────────────────────────────
    async def get_external_profile(self, target: str | None) -> dict:
        """总入口：总返回 dict（available 标志），prompt 直接渲染。

        target 为空 / 未配置 / 熔断 / 失败 → {"available": False, "reason": ...}。
        """
        if not target:
            return {"available": False, "reason": "no_target"}
        base = settings.ARL_PROFILE_BASE_URL
        if not base:
            return {"available": False, "reason": "unconfigured"}

        now = time.monotonic()
        cached = self._cache.get(target)
        if cached and now - cached[0] < settings.ARL_PROFILE_CACHE_TTL:
            return cached[1]

        if self._circuit_open():
            return {"available": False, "reason": "circuit_open"}

        profile = await self._fetch(base, target)
        if profile is None:
            # 防御性契约：_fetch 返回 None 一律视为失败计熔断
            # （内部 except 已计；此处兜底外部 patch/mock 等返回 None 的路径）
            self._record_failure()
            return {"available": False, "reason": "upstream_error"}
        out = self._summarize(profile)
        self._cache[target] = (time.monotonic(), out)
        return out

    # ── 内部 ──────────────────────────────────────────
    async def _fetch(self, base: str, target: str) -> dict | None:
        """调 /api/mcp/asset_profile；成功返回原始画像 dict，失败 None。"""
        try:
            token = await self._ensure_token(base)
            async with httpx.AsyncClient(
                verify=settings.ARL_PROFILE_VERIFY_TLS,
                timeout=settings.ARL_PROFILE_TIMEOUT,
                trust_env=False,  # 同 arl_collector：内网直连，不走系统代理
            ) as client:
                resp = await client.get(
                    f"{base.rstrip('/')}/api/mcp/asset_profile",
                    headers={"Token": token},
                    params={"target": target},
                )
                resp.raise_for_status()
                body = resp.json()
        except Exception as e:  # noqa: BLE001
            logger.warning("ARL 外部画像获取失败 target=%s: %s", target, e)
            self._record_failure()
            return None
        self._record_success()
        return body

    async def _ensure_token(self, base: str) -> str:
        """凭据二选一（与 arl_collector 同契约）：API_KEY 直用；账密 login 换 token。"""
        if settings.ARL_PROFILE_API_KEY:
            return settings.ARL_PROFILE_API_KEY
        u, p = settings.ARL_PROFILE_USERNAME, settings.ARL_PROFILE_PASSWORD
        if not (u and p):
            raise RuntimeError("ARL_PROFILE 凭据未配置（api_key 或 username+password）")
        async with httpx.AsyncClient(
            verify=settings.ARL_PROFILE_VERIFY_TLS,
            timeout=settings.ARL_PROFILE_TIMEOUT,
            trust_env=False,
        ) as client:
            resp = await client.post(
                f"{base.rstrip('/')}/api/user/login",
                json={"username": u, "password": p},
            )
            resp.raise_for_status()
            body = resp.json()
            if body.get("code") != 200:
                raise RuntimeError(f"ARL login 失败 code={body.get('code')}")
            return (body.get("data") or {}).get("token") or ""

    @staticmethod
    def _summarize(profile: dict) -> dict:
        """裁剪为 prompt 友好的摘要（控 token；原始画像不落库，C6）。"""
        ports = [
            {"port": p.get("port"), "service": p.get("service"),
             "product": p.get("product")}
            for p in (profile.get("ports") or [])[:_PORTS_TOP]
            if p.get("port") is not None
        ]
        vulns_all = profile.get("vulns") or []
        return {
            "available": True,
            "source": "arl-next",
            "target": profile.get("target"),
            "resolved_ips": profile.get("resolved_ips"),
            "os": profile.get("os"),
            "ports": ports,
            "ports_total": len(profile.get("ports") or []),
            "web": profile.get("web") if isinstance(profile.get("web"), dict) else None,
            "vulns": [
                {"plugin_name": v.get("plugin_name") or v.get("app_name"),
                 "url": v.get("vuln_url") or v.get("url")}
                for v in vulns_all[:_VULNS_TOP]
            ],
            "vulns_total": len(vulns_all),
            "cert": profile.get("cert") if isinstance(profile.get("cert"), dict) else None,
        }


_client: ARLProfileClient | None = None


def get_arl_profile_client() -> ARLProfileClient:
    """模块级单例（缓存/熔断状态跨请求复用）。"""
    global _client
    if _client is None:
        _client = ARLProfileClient()
    return _client


async def get_external_profile(target: str | None) -> dict:
    """供研判链路调用的模块级入口。"""
    return await get_arl_profile_client().get_external_profile(target)
