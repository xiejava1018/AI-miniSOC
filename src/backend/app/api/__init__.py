"""
API 路由汇总
"""

from fastapi import APIRouter
from app.api import (auth, users, assets, asset_ports, asset_tags, asset_incidents,
    incidents, alerts, ai, ai_chat, ai_agent, menus, roles, departments,
    audit_logs, sync, webhooks, dicts, system_configs, public, notifications,
    ws, data_sync, internal, browsing, alert_digests)

api_router = APIRouter()

# 注册各个模块的路由
api_router.include_router(auth.router, tags=["认证"])
api_router.include_router(users.router, prefix="/users", tags=["用户管理"])
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
