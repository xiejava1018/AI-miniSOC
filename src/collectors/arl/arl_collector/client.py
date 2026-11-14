"""ARL-Next REST 客户端（OH-ARL.1）。

契约依据（docs/design/2026-11-14-ARL-Next集成设计方案.md §2.1/§2.4，v1.4.5 实测）：
  - 认证：Header `Token: <token>`（ARL-Next 自定义头；原版 ARL 的
    `Authorization: Token` 在 v1.4.5 已不生效——实测）。
    支持两种凭据模式：username/password login 换 token（24h 会话，缓存 23h）；
    或独立长期 API_KEY 直填。API_KEY 优先。
  - 成功判据：HTTP 200 **且**响应体 `code === 200`；999=参数错误、104=任务进行中
    （API_GUIDE.md §错误码）。注意归档态 `/api/asset_*` 响应是「扁平 + 顶层 code」
    格式（实测 {"page","size","total","items","code":200}），不是嵌套 envelope。
  - 归档态端点：/api/asset_site/ /api/asset_ip/ /api/asset_vuln/ /
    /api/asset_nuclei_result/ /api/asset_domain/，均支持 scope_id 过滤。
  - 只读：本客户端不调用任何任务创建/停止端点（C3）。
"""

from __future__ import annotations

import ipaddress
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

# 从插件名/应用名提取 CVE 编号（ARL 归档态数据无结构化 cve 字段，实测）
_CVE_RE = re.compile(r"CVE-\d{4}-\d{4,7}", re.IGNORECASE)

# 归档态端点 → 说明（仅文档性）
ASSET_SITES = "asset_site"
ASSET_IPS = "asset_ip"
ASSET_VULNS = "asset_vuln"
ASSET_NUCLEI = "asset_nuclei_result"


class ARLAPIError(RuntimeError):
    """ARL 响应 code != 200（999 参数错误 / 104 任务进行中等）。"""

    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(f"ARL 业务失败 code={code}: {message[:200]}")


class ARLClient:
    """ARL-Next REST 客户端（async httpx，只读）。

    凭据模式（API_KEY 优先）：
      - api_key 模式：每次请求直接带 ``Token: <api_key>``（长期 Key，按制度轮换）；
      - login 模式：POST /api/user/login 换 token，缓存 23h（ARL 会话 24h），
        过期自动重登。
    """

    def __init__(
        self,
        base_url: str,
        username: str | None = None,
        password: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
        verify_tls: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.api_key = api_key
        if not api_key and not (username and password):
            raise ValueError(
                "ARL 凭据缺失：需要 api_key 或 username+password（其一）"
            )
        self.client = httpx.AsyncClient(
            verify=verify_tls,
            timeout=timeout,
            headers={"Content-Type": "application/json"},
        )
        self._token: str | None = None
        self._token_ts: float = 0.0
        self._TOKEN_TTL = 23 * 3600  # ARL 会话 24h，提前 1h 续期

    # ------------------------------------------------------------------
    # 认证
    # ------------------------------------------------------------------
    async def _ensure_token(self) -> str:
        if self.api_key:
            return self.api_key
        now = time.time()
        if self._token and now - self._token_ts < self._TOKEN_TTL:
            return self._token
        resp = await self.client.post(
            f"{self.base_url}/api/user/login",
            json={"username": self.username, "password": self.password},
        )
        resp.raise_for_status()
        body = resp.json()
        # 登录响应是 envelope：{message, code, data:{token}}
        if body.get("code") != 200:
            raise ARLAPIError(body.get("code", -1), body.get("message", "login failed"))
        token = (body.get("data") or {}).get("token")
        if not token:
            raise ARLAPIError(-1, "login 响应缺少 token")
        self._token = token
        self._token_ts = now
        return token

    async def login(self) -> None:
        await self._ensure_token()

    async def logout(self) -> None:
        # ARL-Next 无显式 logout 端点（实测）；token 自然过期。
        # 仅清缓存，强制下轮重登。
        self._token = None
        self._token_ts = 0.0

    # ------------------------------------------------------------------
    # 数据拉取（只读）
    # ------------------------------------------------------------------
    async def fetch_page(
        self, endpoint: str, page: int = 1, size: int = 100,
        extra_params: dict[str, Any] | None = None,
    ) -> dict:
        """GET /api/{endpoint}/ 并校验业务码。

        返回原始 JSON（扁平格式：{page,size,total,items,code}）。
        code != 200 → ARLAPIError（999/104/...）。
        """
        token = await self._ensure_token()
        params: dict[str, Any] = {"page": page, "size": size}
        if extra_params:
            params.update(extra_params)
        resp = await self.client.get(
            f"{self.base_url}/api/{endpoint}/",
            headers={"Token": token},
            params=params,
        )
        resp.raise_for_status()
        body = resp.json()
        code = body.get("code")
        if code != 200:
            raise ARLAPIError(
                code if code is not None else -1,
                str(body.get("message") or body)[:200],
            )
        return body

    async def fetch_all(
        self, endpoint: str, scope_id: str | None = None,
        max_pages: int = 50, page_size: int = 100,
    ) -> list[dict]:
        """分页遍历一个归档态端点。

        max_pages 防失控（数据异常时最多拉 max_pages*size 条）。
        """
        extra = {"scope_id": scope_id} if scope_id else None
        items: list[dict] = []
        for page in range(1, max_pages + 1):
            body = await self.fetch_page(endpoint, page=page, size=page_size,
                                         extra_params=extra)
            batch = body.get("items") or []
            items.extend(batch)
            total = body.get("total") or 0
            if len(batch) < page_size or len(items) >= total:
                break
        return items

    # ------------------------------------------------------------------
    # 规范化（ARL 原始 dict → SOC handler item）
    # ------------------------------------------------------------------
    @staticmethod
    def extract_host_port(url: str) -> tuple[str | None, int | None, str | None]:
        """从站点 URL 提取 (host, port, scheme)。缺省端口按 scheme 补 80/443。"""
        if not url:
            return None, None, None
        try:
            p = urlparse(url if "://" in url else f"http://{url}")
            host = p.hostname
            if not host:
                return None, None, None
            scheme = p.scheme or None
            port = p.port or (443 if scheme == "https" else 80)
            return host, port, scheme
        except ValueError:
            return None, None, None

    @staticmethod
    def extract_cves(*texts: str | None) -> list[str]:
        """从任意文本提取去重后的 CVE 编号列表。"""
        out: list[str] = []
        for t in texts:
            if not t:
                continue
            for m in _CVE_RE.findall(t):
                c = m.upper()
                if c not in out:
                    out.append(c)
        return out

    @staticmethod
    def _observed_at() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _host_to_ip(self, host: str, domain_map: dict[str, str]) -> str | None:
        """host → 可对齐的 IP。host 本身是 IP 则规范化返回；
        是域名则查 asset_ip 数据的 domain 反查映射；无解返回 None（§5.8：
        域名不做资产身份锚，无法对齐的条目丢弃并计数）。"""
        try:
            ipaddress.ip_address(host)
            return host
        except ValueError:
            pass
        return domain_map.get(host.lower())

    async def collect_sites(self, scope_id: str | None = None) -> list[dict]:
        """拉取站点 + IP 资产，规范化为 arl_site items。

        数据源：/api/asset_site/（站点：URL/标题/指纹）+
               /api/asset_ip/（端口：port_info{port_id, service_name, product}）。
        同 (ip, port) 由 ip 资产补 product；域名 host 经 domain_map 解析 IP，
        无解条目跳过（design §5.2 优先级 2 失败 = 优先级 4 不适用——
        发现走确认链路需要 IP，纯域名条目一期丢弃并计入 metadata.skipped_domain_only）。
        """
        sites = await self.fetch_all(ASSET_SITES, scope_id)
        ip_assets = await self.fetch_all(ASSET_IPS, scope_id)

        # domain → ip 反查映射（一个域名多 IP 时取首个）
        domain_map: dict[str, str] = {}
        port_products: dict[tuple[str, int], str] = {}
        ip_type_map: dict[str, str] = {}
        for a in ip_assets:
            ip = str(a.get("ip") or "").strip()
            if not ip:
                continue
            for d in a.get("domain") or []:
                if d and d.lower() not in domain_map:
                    domain_map[str(d).lower()] = ip
            if a.get("ip_type"):
                ip_type_map[ip] = str(a["ip_type"])
            for p in a.get("port_info") or []:
                pid = p.get("port_id")
                if pid and p.get("product"):
                    port_products[(ip, int(pid))] = str(p["product"])

        skipped_domain_only = 0
        items: list[dict] = []
        seen: set[tuple[str, int]] = set()
        now = self._observed_at()

        for s in sites:
            raw_host, port, scheme = self.extract_host_port(str(s.get("site") or ""))
            if not raw_host:
                continue
            ip = self._host_to_ip(raw_host, domain_map)
            if not ip:
                skipped_domain_only += 1
                continue
            key = (ip, port)
            if key in seen:
                continue
            seen.add(key)
            fingers = [
                str(f.get("name"))
                for f in (s.get("finger") or []) if f.get("name")
            ]
            items.append({
                "ip": ip,
                "port": port,
                "scheme": scheme or "http",
                "service": "https" if scheme == "https" else "http",
                "title": s.get("title"),
                "http_status": s.get("status"),
                "url": s.get("site"),
                "fingers": fingers[:20],  # 摘要上限，防 metadata 膨胀（C6）
                "via_domain": raw_host.lower() != ip.lower(),
                "ip_type": ip_type_map.get(ip),
                "scope_id": scope_id,
                "task_id": str(s.get("task_id") or ""),
                "observed_at": now,
            })

        # ip 资产的其余端口（站点未覆盖的）也纳入端口观测
        for a in ip_assets:
            ip = str(a.get("ip") or "").strip()
            if not ip:
                continue
            for p in a.get("port_info") or []:
                pid = p.get("port_id")
                if not pid:
                    continue
                key = (ip, int(pid))
                if key in seen:
                    continue
                seen.add(key)
                svc = str(p.get("service_name") or "")
                items.append({
                    "ip": ip,
                    "port": int(pid),
                    "scheme": "https" if svc == "https" else "http",
                    "service": svc or None,
                    "product": p.get("product"),
                    "ip_type": ip_type_map.get(ip),
                    "scope_id": scope_id,
                    "task_id": str(a.get("task_id") or ""),
                    "observed_at": now,
                })

        self._last_sites_meta = {
            "site_count": len(sites),
            "ip_asset_count": len(ip_assets),
            "skipped_domain_only": skipped_domain_only,
        }
        return items

    async def collect_vulns(self, scope_id: str | None = None) -> list[dict]:
        """拉取漏洞 + nuclei 结果，规范化为 arl_vuln items。

        分流依据（design §5.6 冲突 1）：item 带 cve_ids（从文本提取）且命中
        资产 → 漏洞模型；否则 → soc_scan_findings 旁路（handler 侧逻辑）。
        """
        vulns = await self.fetch_all(ASSET_VULNS, scope_id)
        nuclei = await self.fetch_all(ASSET_NUCLEI, scope_id)

        ip_assets = await self.fetch_all(ASSET_IPS, scope_id)
        domain_map: dict[str, str] = {}
        for a in ip_assets:
            ip = str(a.get("ip") or "").strip()
            for d in a.get("domain") or []:
                if d and d.lower() not in domain_map:
                    domain_map[str(d).lower()] = ip

        skipped_domain_only = 0
        items: list[dict] = []
        now = self._observed_at()

        for v in vulns:
            url = str(v.get("vuln_url") or "")
            raw_host, _port, _scheme = self.extract_host_port(url)
            if not raw_host:
                continue
            ip = self._host_to_ip(raw_host, domain_map)
            if not ip:
                skipped_domain_only += 1
                continue
            items.append({
                "ip": ip,
                "url": url,
                "plugin_name": v.get("plugin_name"),
                "app_name": v.get("app_name"),
                "cve_ids": self.extract_cves(
                    v.get("plugin_name"), v.get("app_name"), url
                ),
                "source_table": "asset_vuln",
                "scope_id": scope_id,
                "task_id": str(v.get("task_id") or ""),
                "observed_at": now,
            })

        for n in nuclei:
            url = str(n.get("url") or n.get("target") or "")
            raw_host, _port, _scheme = self.extract_host_port(url)
            if not raw_host:
                continue
            ip = self._host_to_ip(raw_host, domain_map)
            if not ip:
                skipped_domain_only += 1
                continue
            items.append({
                "ip": ip,
                "url": url,
                "plugin_name": n.get("plugin") or n.get("template_id"),
                "app_name": n.get("info") if isinstance(n.get("info"), str) else None,
                "cve_ids": self.extract_cves(
                    n.get("plugin"), str(n.get("info") or ""), url
                ),
                "severity": n.get("severity"),
                "source_table": "asset_nuclei_result",
                "scope_id": scope_id,
                "task_id": str(n.get("task_id") or ""),
                "observed_at": now,
            })

        self._last_vulns_meta = {
            "vuln_count": len(vulns),
            "nuclei_count": len(nuclei),
            "skipped_domain_only": skipped_domain_only,
        }
        return items

    async def close(self) -> None:
        """释放底层 httpx 客户端（必须与调用方同一事件循环内 await）。"""
        await self.client.aclose()
