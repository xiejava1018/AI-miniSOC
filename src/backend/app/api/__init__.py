"""
API 路由汇总
"""

from fastapi import APIRouter, Depends
from app.api import (auth, users, assets, asset_ports, asset_tags, asset_incidents,
    incidents, alerts, ai, ai_chat, ai_agent, menus, roles, departments,
    audit_logs, sync, webhooks, dicts, system_configs, public, notifications,
    ws, data_sync, internal, browsing, alert_digests, vulnerabilities, dashboard,
    task_observability, asset_risk, asset_query, ai_feedback, knowledge, asset_lifecycle,
    compliance, asset_reconciliation, data_health, reports, impact_analysis)
from app.api.deps import get_current_user

api_router = APIRouter()

# 注册各个模块的路由
api_router.include_router(auth.router, tags=["认证"])
api_router.include_router(users.router, prefix="/users", tags=["用户管理"])
# P3/F2.1 L1：自然语言查询 —— 必须在 assets.router 之前注册，
# 否则 GET /assets/ask 会被 assets 的 GET /{asset_id} 抢匹配（Starlette 按注册顺序）。
api_router.include_router(asset_query.router, prefix="/assets", tags=["AI资产查询"])
# P3/F1.1：风险评分（路径均为 /risk/* 或 /{asset_id}/risk，与 assets 无冲突；
# 先注册保持一致习惯）
api_router.include_router(asset_risk.router, prefix="/assets", tags=["资产风险评分"])
# P3/F3.3：合规基线（/compliance/** 两段以上静态路径；与 lifecycle 同习惯先于 assets 注册）
api_router.include_router(compliance.router, prefix="/assets", tags=["合规基线"])
# P3/F1.3：资产对账（/reconcile** 与 /reconciliations** 两段静态路径，
# 同样必须先于 assets.router，否则 GET /assets/reconciliations 会被 /{asset_id} 抢匹配）
api_router.include_router(asset_reconciliation.router, prefix="/assets", tags=["资产对账"])
api_router.include_router(assets.router, prefix="/assets", tags=["资产管理"])
api_router.include_router(asset_ports.router, prefix="/assets", tags=["资产端口管理"])
api_router.include_router(asset_tags.router, prefix="/assets", tags=["资产标签管理"])
api_router.include_router(asset_incidents.router, prefix="/assets", tags=["资产-事件关联"])
api_router.include_router(incidents.router, prefix="/incidents", tags=["事件管理"])
# 注意：alert_digests 必须在 alerts 之前注册。
# alerts 路由含 catch-all 的 GET /{alert_id}，若不先注册静态的 /groups、/digest，
# 它们会被 /{alert_id} 抢匹配（Starlette 按注册顺序匹配）。
api_router.include_router(alert_digests.router, prefix="/alerts", tags=["告警治理"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["告警管理"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI分析"])
# Art Bot 聊天（SSE 流式）—— 挂在 /ai/chat 下，避免与 /ai/analyze-alert 冲突
api_router.include_router(ai_chat.router, prefix="/ai", tags=["Art Bot"])
# Pi Agent（SSE 流式）—— 挂在 /ai/agent 下
api_router.include_router(ai_agent.router, prefix="/ai", tags=["Pi Agent"])
# P3/F4.1：AI 反馈闭环（👍/👎，所有 AI 产物通用）
api_router.include_router(ai_feedback.router, prefix="/ai", tags=["AI反馈"])
# P3/F2.3：运维知识库（搜索/列表/CRUD/验证/自动提取）
api_router.include_router(
    knowledge.router,
    prefix="/knowledge",
    tags=["运维知识库"],
    dependencies=[Depends(get_current_user)],
)
# P3/F3.2：生命周期（/lifecycle/* 两段静态路径，须先于 assets.router 注册防 /{asset_id} 抢匹配）
api_router.include_router(asset_lifecycle.router, prefix="/assets", tags=["资产生命周期"])
# P3/F1.3：数据健康聚合（顶级 /data-health）。
# source_health / sync_dead_letter 之前只有后台任务在写表、从未有 API，这里是它们的首个出口。
api_router.include_router(impact_analysis.router, prefix="/assets", tags=["变更影响分析"])
api_router.include_router(data_health.router, tags=["数据健康"])
api_router.include_router(reports.router, tags=["AI安全报告"])
api_router.include_router(menus.router, prefix="/menus", tags=["菜单管理"])
api_router.include_router(roles.router, prefix="/roles", tags=["角色管理"])
api_router.include_router(departments.router, prefix="/departments", tags=["部门管理"])
api_router.include_router(audit_logs.router, tags=["审计日志管理"])
api_router.include_router(sync.router, prefix="/sync", tags=["资产同步"])
api_router.include_router(webhooks.router, prefix="/webhooks", tags=["Webhooks"])
api_router.include_router(dicts.router, prefix="/dicts", tags=["字典管理"])
api_router.include_router(system_configs.router, prefix="/system-configs", tags=["系统配置"])
api_router.include_router(notifications.router, tags=["站内通知"])
api_router.include_router(ws.router, tags=["WebSocket"])
# public 接口（不鉴权；前缀 /public 显式标注，避免误以为受保护）
api_router.include_router(public.router, prefix="/public", tags=["公共信息"])
# Collector 数据同步接口（API Key 认证，非 JWT）
api_router.include_router(data_sync.router, prefix="/data", tags=["数据同步"])
# 内部 Agent 工具（Service Token 认证，只读）
api_router.include_router(internal.tools.router)
# 上网行为异常检测
api_router.include_router(browsing.router, prefix="/browsing", tags=["行为检测"])
# 脆弱性管理（T1，2026-08-15 点亮：原端点零鉴权，且含写操作，注册时统一加鉴权依赖）
api_router.include_router(
    vulnerabilities.router,
    prefix="/vulnerabilities",
    tags=["脆弱性管理"],
    dependencies=[Depends(get_current_user)],
)
# 概览仪表板（聚合接口，端点内部已用 get_current_user 鉴权 + RBAC 裁剪）
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["概览仪表板"])
# 后台任务可观测性（v0.4.2 Phase 1.3）
api_router.include_router(
    task_observability.router,
    dependencies=[Depends(get_current_user)],
)
