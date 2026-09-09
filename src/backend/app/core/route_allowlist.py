"""
路由分类白名单

精确到 method+path：
- ``PUBLIC_API_PATHS``：人类公开 API（无需任何认证）。
- ``MACHINE_API_PREFIXES``：机器通道（API Key/Webhook 等），按前缀匹配。

任何路由分类变更必须先改这里，并经安全负责人评审（见 PRD §八 Q3）。
"""



# ---------------------------------------------------------------------------
# 公开 API：精确到 (method, path)
# ---------------------------------------------------------------------------

PUBLIC_API_PATHS: frozenset[tuple[str, str]] = frozenset(
    {
        # 认证流程
        ("POST", "/api/v1/auth/login"),
        ("GET", "/api/v1/auth/captcha"),
        ("POST", "/api/v1/auth/refresh"),
        # 系统自描述（公开信息）
        ("GET", "/api/v1/public/system-info"),
        # 健康检查
        ("GET", "/health"),
        ("GET", "/"),
        # 文档（FastAPI 自动挂载）
        ("GET", "/docs"),
        ("GET", "/docs/oauth2-redirect"),
        ("GET", "/redoc"),
        ("GET", "/openapi.json"),
        # Prometheus 抓取（metrics 自身无鉴权；挂在 /metrics 而非 /api 下）
        ("GET", "/metrics"),
    }
)


# ---------------------------------------------------------------------------
# 机器通道：按前缀匹配
# ---------------------------------------------------------------------------

MACHINE_API_PREFIXES: frozenset[str] = frozenset(
    {
        # Webhook（Wazuh 推送，使用 IP 白名单 + 共享 Key，非 JWT）
        "/api/v1/webhooks/",
        # 采集器推送（X-API-Key）
        "/api/v1/data/",
        # 扫描器通道（独立 API Key）
        "/api/v1/scan/agents/",
        # 内部 Agent 工具（Service Token）
        "/internal/",
        "/api/v1/internal/",
        # WebSocket 鉴权（query string token，单独实现）
        "/api/v1/ws/",
        "/ws/",
        # 健康检查与监控
        "/health",
        "/metrics",
    }
)


# ---------------------------------------------------------------------------
# 扫描器回调子路径：精确到前缀 + 子路径的组合
# 例如 `/api/v1/scan/tasks/{uuid}/claim` 与 `/api/v1/scan/tasks/{uuid}/report`
# 走扫描器独立 API Key，但人类 scan_tasks 路由以 `/api/v1/scan/tasks/...` 为前缀，
# 二者区分需要走子路径匹配。
# ---------------------------------------------------------------------------

SCANNER_CALLBACK_SUBPATHS: frozenset[str] = frozenset(
    {
        "/agents/heartbeat",  # POST /api/v1/scan/agents/heartbeat
        "/tasks/pending",     # GET  /api/v1/scan/tasks/pending
        "/claim",             # PATCH /api/v1/scan/tasks/{uuid}/claim
        "/report",            # PATCH /api/v1/scan/tasks/{uuid}/report
    }
)


def is_scanner_callback(path: str) -> bool:
    """判断某条人类路由路径是不是扫描器回调（用 scanner 独立 API Key 而非 JWT）。"""
    if not path.startswith("/api/v1/scan/"):
        return False
    return any(sub in path for sub in SCANNER_CALLBACK_SUBPATHS)


# ---------------------------------------------------------------------------
# 仅允许 viewer 执行的写例外：精确到 (method, path)
# ---------------------------------------------------------------------------

SESSION_WRITE_PATHS: frozenset[tuple[str, str]] = frozenset(
    {
        ("POST", "/api/v1/auth/logout"),
    }
)


def is_public(method: str, path: str) -> bool:
    return (method.upper(), path) in PUBLIC_API_PATHS


def is_machine(method: str, path: str) -> bool:
    return any(path.startswith(prefix) for prefix in MACHINE_API_PREFIXES)


def is_session_write(method: str, path: str) -> bool:
    return (method.upper(), path) in SESSION_WRITE_PATHS