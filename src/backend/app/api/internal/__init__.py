"""
Internal Agent Tools API

提供三个只读 SOC 工具供 AI Agent 调用:
- query_assets: 查询资产列表
- query_alerts: 查询 Wazuh 告警
- search_logs: 查询 Loki 日志

认证: X-Service-Token 请求头校验
"""

from app.api.internal import tools