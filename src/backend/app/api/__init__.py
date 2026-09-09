"""
API 路由汇总

集中注册所有路由，并使用 ``include_human_router`` 统一挂载 WO-1/WO-2 的安全依赖：

- 人类业务路由：默认挂 ``get_current_user``（读端点）+ ``enforce_write_default``（写端点）
- 公开/机器通道：进入 ``route_allowlist`` 白名单，不挂 JWT 依赖

所有路由的最终分类以 ``route_allowlist`` + ``route_security`` 的扫描结果为准，
CI 步骤 ``tests/security/test_route_authorization.py`` 会校验每个 method+path
都命中 public/machine/human 三类之一，且人类写端点有显式授权依赖。
"""

from fastapi import APIRouter, Depends

from app.api import (
    auth, users, assets, behavior_profile, asset_ports, asset_tags, asset_incidents,
    incidents, alerts, ai, ai_chat, ai_agent, menus, roles, departments,
    audit_logs, sync, webhooks, dicts, system_configs, public, notifications,
    ws, data_sync, internal, browsing, alert_digests, vulnerabilities, dashboard,
    task_observability, asset_risk, asset_query, ai_feedback, knowledge, asset_lifecycle,
    compliance, asset_reconciliation, data_health, reports, impact_analysis,
    scan_agents, scan_human_agents, scan_tasks,
)
from app.core.auth import get_current_user
from app.core.route_security import enforce_write_default


api_router = APIRouter()


# ---------------------------------------------------------------------------
# include_human_router：人类业务路由的集中挂载点
# ---------------------------------------------------------------------------

def include_human_router(
    parent: APIRouter,
    router,
    *,
    prefix: str = "",
    tags: list[str] | None = None,
    extra_dependencies: list | None = None,
) -> None:
    """统一挂载人类业务路由。

    - 默认 router 级 ``get_current_user``（读端点必须登录）
    - 默认 router 级 ``enforce_write_default``（写端点挡 viewer/readonly，
      未带显式授权的写路由由 ``enforce_write_default`` 兜底）

    Args:
        parent: 要把子路由注册到的父 router
        router: 子 router（来自各业务模块）
        prefix: 子路由前缀（如 ``"/users"``）
        tags: OpenAPI 标签
        extra_dependencies: 额外 router 级依赖（通常不需）
    """
    deps = [
        Depends(get_current_user),
        Depends(enforce_write_default),
    ]
    if extra_dependencies:
        deps.extend(extra_dependencies)

    parent.include_router(
        router,
        prefix=prefix,
        tags=tags or router.tags,
        dependencies=deps,
    )


# ---------------------------------------------------------------------------
# 注册顺序：先注册窄路径前缀（避免被宽路径 catch-all 抢匹配）
# ---------------------------------------------------------------------------

# 1. 公开路由（无需鉴权）
api_router.include_router(public.router, prefix="/public", tags=["公共信息"])

# 2. 机器通道（API Key/Webhook/Service Token）
api_router.include_router(auth.router, tags=["认证"])  # auth 内有公开 + 登出；本身不需 router 级 JWT
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(data_sync.router, prefix="/data", tags=["数据同步"])
api_router.include_router(scan_agents.router, prefix="/scan", tags=["扫描器控制面"])
api_router.include_router(internal.tools.router)
api_router.include_router(ws.router, tags=["WebSocket"])

# 3. 人类业务路由（统一挂 get_current_user + enforce_write_default）
# 注册顺序必须保留原有的"窄前缀先注册"约定，避免被 /{asset_id} / {id} catch-all 抢匹配。
include_human_router(
    api_router, asset_query.router, prefix="/assets", tags=["AI资产查询"],
)
include_human_router(
    api_router, asset_risk.router, prefix="/assets", tags=["资产风险评分"],
)
include_human_router(
    api_router, compliance.router, prefix="/assets", tags=["合规基线"],
)
include_human_router(
    api_router, asset_reconciliation.router, prefix="/assets", tags=["资产对账"],
)
include_human_router(
    api_router, assets.router, prefix="/assets", tags=["资产管理"],
)
include_human_router(
    api_router, asset_ports.router, prefix="/assets", tags=["资产端口管理"],
)
include_human_router(
    api_router, asset_tags.router, prefix="/assets", tags=["资产标签管理"],
)
include_human_router(
    api_router, asset_incidents.router, prefix="/assets", tags=["资产-事件关联"],
)
include_human_router(
    api_router, asset_lifecycle.router, prefix="/assets", tags=["资产生命周期"],
)
include_human_router(
    api_router, impact_analysis.router, prefix="/assets", tags=["变更影响分析"],
)

# 用户管理（含登录态读 + admin 写）
include_human_router(api_router, users.router, prefix="/users", tags=["用户管理"])

# 事件管理（业务写，需要 operator/user/admin；读 viewer 放行）
include_human_router(api_router, incidents.router, prefix="/incidents", tags=["事件管理"])

# 告警治理 + 告警管理（注意 alert_digests 必须在 alerts 之前注册，否则 /{alert_id} 抢匹配）
include_human_router(
    api_router, alert_digests.router, prefix="/alerts", tags=["告警治理"],
)
include_human_router(
    api_router, alerts.router, prefix="/alerts", tags=["告警管理"],
)

# AI 相关
include_human_router(api_router, ai.router, prefix="/ai", tags=["AI分析"])
include_human_router(api_router, ai_chat.router, prefix="/ai", tags=["Art Bot"])
include_human_router(api_router, ai_agent.router, prefix="/ai", tags=["Pi Agent"])
include_human_router(api_router, ai_feedback.router, prefix="/ai", tags=["AI反馈"])

# 知识库 / 脆弱性 / 任务可观测性
include_human_router(
    api_router, knowledge.router, prefix="/knowledge", tags=["运维知识库"],
)
include_human_router(
    api_router, vulnerabilities.router, prefix="/vulnerabilities", tags=["脆弱性管理"],
)
include_human_router(
    api_router, task_observability.router, tags=["任务可观测性"],
)

# 数据健康 / 行为画像 / 报告
include_human_router(api_router, data_health.router, tags=["数据健康"])
include_human_router(api_router, behavior_profile.router, tags=["行为画像"])
include_human_router(api_router, reports.router, tags=["AI安全报告"])
# 上网行为异常检测（browsing 模块 endpoint 形如 /events /blacklist /baseline 等，
# 需在前缀 /browsing 下挂载；写端点依赖 require_admin/operator 已在 browsing.py 内部声明）
include_human_router(api_router, browsing.router, prefix="/browsing", tags=["行为检测"])

# 扫描器管理 + 扫描任务（人类侧，与 scan_agents 的机器侧区分）
include_human_router(
    api_router, scan_human_agents.router, prefix="/scan", tags=["扫描器管理"],
)
include_human_router(
    api_router, scan_tasks.router, prefix="/scan", tags=["扫描任务"],
)

# 系统管理（菜单/角色/部门/审计日志/字典/系统配置/通知）—— 写操作均 admin-only
include_human_router(api_router, menus.router, prefix="/menus", tags=["菜单管理"])
include_human_router(api_router, roles.router, prefix="/roles", tags=["角色管理"])
include_human_router(
    api_router, departments.router, prefix="/departments", tags=["部门管理"],
)
include_human_router(api_router, audit_logs.router, tags=["审计日志管理"])
include_human_router(api_router, dicts.router, prefix="/dicts", tags=["字典管理"])
include_human_router(
    api_router, system_configs.router, prefix="/system-configs", tags=["系统配置"],
)
include_human_router(api_router, notifications.router, tags=["站内通知"])

# 同步任务管理（人类侧触发；Wazuh 推送走 webhooks）
include_human_router(api_router, sync.router, prefix="/sync", tags=["资产同步"])

# 概览仪表板（get_dashboard_trend 原本无鉴权，现已在 dashboard.py 内挂 Depends(get_current_user)）
include_human_router(
    api_router, dashboard.router, prefix="/dashboard", tags=["概览仪表板"],
)