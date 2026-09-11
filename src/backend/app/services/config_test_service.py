"""测试连接服务（ConfigTestService）

设计依据：docs/design/2026-09-11-配置中心详细设计规格.md §5.8

按 source_type 探测外部系统，返回结构化结果：
  - ok        : 总判定
  - latency_ms: 总耗时
  - checks    : 各项检查的明细
  - details   : 自由信息（如 Wazuh api_version）
  - message   : 总说明

约束：
- 超时取 min(timeout_seconds, 15)，硬上限 15s
- verify_ssl=False 时 httpx.Client(verify=False)
- 任何异常都要捕获并转为 ok=false + 可读 message，不得抛 500
- 不产生副作用（Wazuh 仅只读 GET；tplink 仅 TCP 探测，不做真实登录）
"""

import logging
import socket
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx

from app.schemas.data_source import TestCheck, TestConnectionResponse

logger = logging.getLogger(__name__)

_HARD_TIMEOUT_CAP = 15  # 秒，硬上限


def _cap_timeout(timeout: int) -> float:
    try:
        return float(min(int(timeout), _HARD_TIMEOUT_CAP))
    except (TypeError, ValueError):
        return float(_HARD_TIMEOUT_CAP)


def _safe_endpoint(endpoint: str) -> str:
    e = (endpoint or "").rstrip("/")
    if not e:
        raise ValueError("endpoint 不能为空")
    return e


class ConfigTestService:
    def __init__(self, db=None):
        self.db = db

    def test(
        self,
        *,
        source_type: str,
        endpoint: str,
        auth_type: str,
        auth_username: Optional[str],
        auth_secret: Optional[str],
        verify_ssl: bool,
        timeout_seconds: int,
        config_json: Optional[Dict[str, Any]] = None,
    ) -> TestConnectionResponse:
        """根据 source_type 分发到具体探测。"""
        try:
            endpoint_clean = _safe_endpoint(endpoint)
        except ValueError as e:
            return TestConnectionResponse(
                ok=False,
                latency_ms=0,
                message=str(e),
                checks=[],
                details={},
            )

        t0 = time.time()
        try:
            if source_type == "wazuh":
                result = self._test_wazuh(
                    endpoint_clean,
                    auth_type,
                    auth_username,
                    auth_secret,
                    verify_ssl,
                    timeout_seconds,
                )
            elif source_type == "opensearch":
                result = self._test_opensearch(
                    endpoint_clean,
                    auth_type,
                    auth_username,
                    auth_secret,
                    verify_ssl,
                    timeout_seconds,
                )
            elif source_type == "loki":
                result = self._test_loki(endpoint_clean, verify_ssl, timeout_seconds)
            elif source_type == "tplink":
                result = self._test_tplink(endpoint_clean, timeout_seconds)
            elif source_type == "scanner":
                result = self._test_scanner(endpoint_clean, verify_ssl, timeout_seconds)
            else:
                return TestConnectionResponse(
                    ok=False,
                    latency_ms=int((time.time() - t0) * 1000),
                    message=f"未实现的 source_type: {source_type}",
                    checks=[],
                    details={},
                )
        except Exception as e:
            logger.exception("测试连接异常: source_type=%s, err=%s", source_type, e)
            return TestConnectionResponse(
                ok=False,
                latency_ms=int((time.time() - t0) * 1000),
                message=f"测试异常：{type(e).__name__}: {e}",
                checks=[],
                details={},
            )

        result.latency_ms = int((time.time() - t0) * 1000)
        return result

    # ---------------- Wazuh ----------------

    def _test_wazuh(
        self,
        endpoint: str,
        auth_type: str,
        username: Optional[str],
        password: Optional[str],
        verify_ssl: bool,
        timeout_seconds: int,
    ) -> TestConnectionResponse:
        checks: List[TestCheck] = []
        details: Dict[str, Any] = {}
        timeout = _cap_timeout(timeout_seconds)

        if auth_type != "basic":
            checks.append(
                TestCheck(name="认证", ok=False, message=f"Wazuh 仅支持 basic，当前 {auth_type}")
            )
            return TestConnectionResponse(
                ok=False,
                latency_ms=0,
                message="认证方式不支持",
                checks=checks,
                details=details,
            )

        try:
            with httpx.Client(verify=verify_ssl, timeout=timeout) as client:
                # 1) authenticate
                token: Optional[str] = None
                try:
                    resp = client.post(
                        f"{endpoint}/security/user/authenticate",
                        auth=(username or "", password or ""),
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.status_code == 200:
                        data = resp.json() or {}
                        token = (data.get("data") or {}).get("token")
                        checks.append(
                            TestCheck(
                                name="认证",
                                ok=bool(token),
                                message="JWT 获取成功" if token else "返回 200 但无 token",
                            )
                        )
                    else:
                        checks.append(
                            TestCheck(
                                name="认证",
                                ok=False,
                                message=f"HTTP {resp.status_code}",
                            )
                        )
                except httpx.HTTPError as e:
                    checks.append(TestCheck(name="认证", ok=False, message=str(e)))

                if not token:
                    return TestConnectionResponse(
                        ok=False,
                        latency_ms=0,
                        message="认证失败，无法继续探测",
                        checks=checks,
                        details=details,
                    )

                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                }

                # 2) version
                try:
                    resp = client.get(f"{endpoint}/", headers=headers)
                    if resp.status_code == 200:
                        body = resp.json() or {}
                        api_version = body.get("data", {}).get("api_version") or body.get(
                            "api_version"
                        )
                        details["api_version"] = api_version
                        checks.append(
                            TestCheck(
                                name="版本",
                                ok=bool(api_version),
                                message=str(api_version) if api_version else "无 api_version 字段",
                            )
                        )
                    else:
                        checks.append(
                            TestCheck(name="版本", ok=False, message=f"HTTP {resp.status_code}")
                        )
                except httpx.HTTPError as e:
                    checks.append(TestCheck(name="版本", ok=False, message=str(e)))

                # 3) agents
                try:
                    resp = client.get(
                        f"{endpoint}/agents", params={"limit": 1}, headers=headers
                    )
                    if resp.status_code == 200:
                        body = resp.json() or {}
                        items = (
                            body.get("data", {}).get("affected_items")
                            or body.get("affected_items")
                            or []
                        )
                        checks.append(
                            TestCheck(
                                name="Agents 接口",
                                ok=True,
                                message=f"返回 {len(items)} 条",
                            )
                        )
                    else:
                        checks.append(
                            TestCheck(
                                name="Agents 接口",
                                ok=False,
                                message=f"HTTP {resp.status_code}",
                            )
                        )
                except httpx.HTTPError as e:
                    checks.append(TestCheck(name="Agents 接口", ok=False, message=str(e)))

                # 4) vulnerability（探测：本环境可能 404，不影响总判定）
                try:
                    resp = client.get(
                        f"{endpoint}/vulnerability",
                        params={"limit": 1},
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        checks.append(
                            TestCheck(name="漏洞接口", ok=True, message="可访问")
                        )
                    else:
                        checks.append(
                            TestCheck(
                                name="漏洞接口",
                                ok=False,
                                message=(
                                    f"HTTP {resp.status_code} — 本环境不支持，CVE 走 OpenSearch"
                                    if resp.status_code == 404
                                    else f"HTTP {resp.status_code}"
                                ),
                            )
                        )
                except httpx.HTTPError as e:
                    checks.append(TestCheck(name="漏洞接口", ok=False, message=str(e)))

                ok_overall = checks[0].ok and (
                    checks[1].ok if len(checks) > 1 else True
                )  # 认证 + 版本
                # 总判定：前三项通过即可
                ok_overall = (
                    checks[0].ok
                    and (len(checks) > 1 and checks[1].ok)
                    and (len(checks) > 2 and checks[2].ok)
                )

                message = "连接成功" if ok_overall else "连接失败，详见检查项"
                return TestConnectionResponse(
                    ok=ok_overall,
                    latency_ms=0,
                    message=message,
                    checks=checks,
                    details=details,
                )
        except Exception as e:
            logger.exception("Wazuh 测试连接异常: %s", e)
            checks.append(TestCheck(name="异常", ok=False, message=str(e)))
            return TestConnectionResponse(
                ok=False, latency_ms=0, message=str(e), checks=checks, details=details
            )

    # ---------------- OpenSearch ----------------

    def _test_opensearch(
        self,
        endpoint: str,
        auth_type: str,
        username: Optional[str],
        password: Optional[str],
        verify_ssl: bool,
        timeout_seconds: int,
    ) -> TestConnectionResponse:
        checks: List[TestCheck] = []
        details: Dict[str, Any] = {}
        timeout = _cap_timeout(timeout_seconds)

        auth = (
            (username or "", password or "")
            if auth_type == "basic" and (username or password)
            else None
        )

        try:
            with httpx.Client(verify=verify_ssl, timeout=timeout, auth=auth) as client:
                # 1) root
                try:
                    resp = client.get(f"{endpoint}/")
                    if resp.status_code == 200:
                        body = resp.json() or {}
                        details["version"] = body.get("version", {}).get("number")
                        details["cluster_name"] = body.get("cluster_name")
                        checks.append(
                            TestCheck(
                                name="根信息",
                                ok=True,
                                message=f"version={details.get('version')}",
                            )
                        )
                    else:
                        checks.append(
                            TestCheck(
                                name="根信息", ok=False, message=f"HTTP {resp.status_code}"
                            )
                        )
                        return TestConnectionResponse(
                            ok=False, latency_ms=0, message="根信息失败", checks=checks, details=details
                        )
                except httpx.HTTPError as e:
                    checks.append(TestCheck(name="根信息", ok=False, message=str(e)))
                    return TestConnectionResponse(
                        ok=False, latency_ms=0, message=str(e), checks=checks, details=details
                    )

                # 2) cluster health
                try:
                    resp = client.get(f"{endpoint}/_cluster/health")
                    if resp.status_code == 200:
                        body = resp.json() or {}
                        status_val = body.get("status")
                        details["cluster_status"] = status_val
                        msg = f"status={status_val}"
                        ok = status_val in ("green", "yellow", "red")  # 即使 red 也告警但 ok
                        if status_val == "red":
                            msg = f"{msg}（集群状态 red，请关注）"
                        checks.append(TestCheck(name="集群健康", ok=ok, message=msg))
                    else:
                        checks.append(
                            TestCheck(
                                name="集群健康",
                                ok=False,
                                message=f"HTTP {resp.status_code}",
                            )
                        )
                except httpx.HTTPError as e:
                    checks.append(TestCheck(name="集群健康", ok=False, message=str(e)))

                ok_overall = len(checks) > 0 and checks[0].ok
                message = "连接成功" if ok_overall else "连接失败"
                return TestConnectionResponse(
                    ok=ok_overall,
                    latency_ms=0,
                    message=message,
                    checks=checks,
                    details=details,
                )
        except Exception as e:
            logger.exception("OpenSearch 测试连接异常: %s", e)
            return TestConnectionResponse(
                ok=False,
                latency_ms=0,
                message=str(e),
                checks=[TestCheck(name="异常", ok=False, message=str(e))],
                details=details,
            )

    # ---------------- Loki ----------------

    def _test_loki(
        self,
        endpoint: str,
        verify_ssl: bool,
        timeout_seconds: int,
    ) -> TestConnectionResponse:
        checks: List[TestCheck] = []
        timeout = _cap_timeout(timeout_seconds)
        try:
            with httpx.Client(verify=verify_ssl, timeout=timeout) as client:
                # 1) ready
                try:
                    resp = client.get(f"{endpoint}/ready")
                    ok = resp.status_code == 200
                    checks.append(
                        TestCheck(
                            name="Ready",
                            ok=ok,
                            message="ready" if ok else f"HTTP {resp.status_code}",
                        )
                    )
                except httpx.HTTPError as e:
                    checks.append(TestCheck(name="Ready", ok=False, message=str(e)))

                # 2) labels
                try:
                    resp = client.get(f"{endpoint}/loki/api/v1/labels")
                    if resp.status_code == 200:
                        body = resp.json() or {}
                        labels = body.get("data") or []
                        checks.append(
                            TestCheck(
                                name="标签枚举", ok=True, message=f"{len(labels)} 个标签"
                            )
                        )
                    else:
                        checks.append(
                            TestCheck(
                                name="标签枚举",
                                ok=False,
                                message=f"HTTP {resp.status_code}",
                            )
                        )
                except httpx.HTTPError as e:
                    checks.append(TestCheck(name="标签枚举", ok=False, message=str(e)))

                ok_overall = len(checks) > 0 and checks[0].ok
                message = "连接成功" if ok_overall else "连接失败"
                return TestConnectionResponse(
                    ok=ok_overall,
                    latency_ms=0,
                    message=message,
                    checks=checks,
                    details={},
                )
        except Exception as e:
            logger.exception("Loki 测试连接异常: %s", e)
            return TestConnectionResponse(
                ok=False,
                latency_ms=0,
                message=str(e),
                checks=[TestCheck(name="异常", ok=False, message=str(e))],
                details={},
            )

    # ---------------- TP-Link（仅 TCP 探测）----------------

    def _test_tplink(self, endpoint: str, timeout_seconds: int) -> TestConnectionResponse:
        try:
            parsed = urlparse(endpoint)
            host = parsed.hostname
            port = parsed.port or 80
        except Exception as e:
            return TestConnectionResponse(
                ok=False,
                latency_ms=0,
                message=f"endpoint 解析失败：{e}",
                checks=[],
                details={},
            )
        if not host:
            return TestConnectionResponse(
                ok=False,
                latency_ms=0,
                message="缺少 host",
                checks=[],
                details={},
            )
        timeout = _cap_timeout(timeout_seconds)
        try:
            with socket.create_connection((host, port), timeout=timeout) as _:
                return TestConnectionResponse(
                    ok=True,
                    latency_ms=0,
                    message=f"TCP {host}:{port} 可达",
                    checks=[
                        TestCheck(name="TCP 连通性", ok=True, message=f"{host}:{port}")
                    ],
                    details={"host": host, "port": port},
                )
        except Exception as e:
            return TestConnectionResponse(
                ok=False,
                latency_ms=0,
                message=str(e),
                checks=[TestCheck(name="TCP 连通性", ok=False, message=str(e))],
                details={"host": host, "port": port},
            )

    # ---------------- Scanner（仅 GET /health）----------------

    def _test_scanner(
        self, endpoint: str, verify_ssl: bool, timeout_seconds: int
    ) -> TestConnectionResponse:
        timeout = _cap_timeout(timeout_seconds)
        try:
            with httpx.Client(verify=verify_ssl, timeout=timeout) as client:
                resp = client.get(f"{endpoint}/health")
                ok = resp.status_code == 200
                return TestConnectionResponse(
                    ok=ok,
                    latency_ms=0,
                    message="健康检查通过" if ok else f"HTTP {resp.status_code}",
                    checks=[
                        TestCheck(
                            name="健康检查",
                            ok=ok,
                            message="ok" if ok else f"HTTP {resp.status_code}",
                        )
                    ],
                    details={"status_code": resp.status_code},
                )
        except Exception as e:
            return TestConnectionResponse(
                ok=False,
                latency_ms=0,
                message=str(e),
                checks=[TestCheck(name="健康检查", ok=False, message=str(e))],
                details={},
            )