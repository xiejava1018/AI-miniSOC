"""
AI-miniSOC MCP Server 工厂（纯 C 路线）。

历史：本项目原本是 B+C 混搭，B 部分用 fastapi-mcp 从 OpenAPI 自动生成 23 个 tool。
2026-08-08 决定全 C：
  1) B 依赖库脆弱（cycle patch + monkey-patch 难维护）
  2) Agent 实际只用到 7/23 个 B tool，剩下都是后台管理
  3) 全 C tool 名字短，上下文省 ~70%
如需重新启用 B，恢复原文件备份 + `_collect_safe_operation_ids` + `FastApiMCP`。

当前架构：
- FastMCP 实例启动所有手写 tool（28 个）
- FastMCP 独立跑 SSE transport（后台线程），端口 8100
- 主服务 8000 不受影响
"""
from __future__ import annotations

import logging
import threading
from typing import Any

import uvicorn
from fastapi import FastAPI

from app.mcp.tools import register_all

logger = logging.getLogger(__name__)


def mount_mcp(_app: FastAPI, mount_path: str = "/mcp") -> dict[str, Any]:
    """
    挂载 MCP Server 到项目（实际只起 FastMCP SSE server，不挂载到 FastAPI app）。

    Args:
        _app: FastAPI app（保留参数兼容性，实际不用）
        mount_path: 占位参数（之前给 B 部分用，保留兼容）
    """
    info: dict[str, Any] = {"endpoints": {}}

    from mcp.server.fastmcp import FastMCP

    custom_mcp = FastMCP(
        name="AI-miniSOC MCP",
        instructions=(
            "AI-miniSOC 的精选工具集。包括 token 管理、系统信息、AI 分析、Loki 直连、"
            "资产 / 告警 / 事件查询与创建、字典查询。\n\n"
            "**推荐调用流程**：\n"
            "1. get_system_info 自我介绍\n"
            "2. set_mcp_credentials(username, password) 配置凭证\n"
            "3. 后续所有工具自动复用凭证，无需关心 token 过期\n"
        ),
    )
    register_all(custom_mcp)

    # 提取手写 tools 列表（用于文档/日志）
    try:
        custom_tools = await_get_custom_tools(custom_mcp)
        info["custom_tools"] = custom_tools
        logger.info("MCP-C: 手写 tools (%d 个): %s", len(custom_tools), custom_tools)
    except Exception as e:  # noqa: BLE001
        logger.warning("枚举手写 tools 失败: %s", e)

    # FastMCP 独立 SSE server，端口 8100
    # 测试/开发环境可通过 MCP_SSE_ENABLED=false 关闭，避免端口冲突
    import os as _os
    if _os.getenv("MCP_SSE_ENABLED", "true").lower() in ("false", "0", "no"):
        logger.info("MCP SSE server disabled by MCP_SSE_ENABLED=false")
        info["endpoints"]["mcp_sse_url"] = ""
        info["mount_path_unused"] = mount_path
        return info

    custom_mcp.settings.host = "0.0.0.0"
    custom_mcp.settings.port = 8100
    # sse_app("/") 让 endpoint URL 与实际路由都是 /messages/，避免 307 重定向
    starlette_app = custom_mcp.sse_app("/")

    def _run_mcp() -> None:
        try:
            config = uvicorn.Config(
                starlette_app,
                host="0.0.0.0",
                port=8100,
                log_level="info",
                lifespan="on",
            )
            server = uvicorn.Server(config)
            server.run()
        except Exception as e:  # noqa: BLE001
            logger.error("MCP SSE server 异常退出: %s", e)

    t = threading.Thread(target=_run_mcp, name="mcp-sse-server", daemon=True)
    t.start()
    logger.info("MCP SSE server starting on http://0.0.0.0:8100/sse (SSE transport)")

    info["endpoints"]["mcp_sse_url"] = "http://0.0.0.0:8100/sse"
    info["mount_path_unused"] = mount_path  # 保留参数兼容性

    return info


def await_get_custom_tools(mcp_instance) -> list[str]:
    """同步枚举 FastMCP 实例的所有 tool 名（不实际调用）"""
    try:
        manager = getattr(mcp_instance, "_tool_manager", None)
        if manager is not None:
            return sorted(manager._tools.keys())  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass
    return []


# ============================================================================
# 历史备份：B 部分代码（已禁用，仅供参考）
# ============================================================================
# 如需重新启用 fastapi-mcp 自动从 OpenAPI 生成 tools：
# 1) 恢复以下 import:
#       from fastapi_mcp import FastApiMCP
# 2) 取消 mount_mcp 中 B 部分的注释
# 3) 添加白名单 SAFE_OPENAPI_OPS
# 4) 重新打 fastapi_mcp/openapi/utils.py cycle-detection 补丁
# ============================================================================
SAFE_OPENAPI_OPS_DISABLED: list[str] = [
    # 原 B 部分 23 个 tool 白名单（已废弃，保留作参考）
    # "get_public_system_info_api_v1_public_system_info_get",
    # "get_users_api_v1_users_get",
    # "get_user_api_v1_users__user_id__get",
    # "get_roles_api_v1_roles_get",
    # "get_role_api_v1_roles__role_id__get",
    # "get_menus_api_v1_menus_get",
    # "get_menu_tree_api_v1_menus_tree_get",
    # "get_menu_options_api_v1_menus_options_get",
    # "get_departments_api_v1_departments_get",
    # "get_department_api_v1_departments__department_id__get",
    # "get_department_tree_api_v1_departments_tree_get",
    # "list_asset_ports_api_v1_assets__asset_id__ports_get",
    # "get_asset_overview_api_v1_assets_overview_get",
    # "get_asset_sources_api_v1_assets__asset_id__sources_get",
    # "get_dict_list_api_v1_dicts_get",
    # "get_dict_types_api_v1_dicts_types_get",
    # "get_dicts_by_type_api_v1_dicts__dict_type__items_get",
    # "get_config_list_api_v1_system_configs_get",
    # "get_config_categories_api_v1_system_configs_categories_get",
    # "get_audit_logs_api_v1_audit_logs_get",
    # "get_audit_log_api_v1_audit_logs__log_id__get",
    # "list_notifications_api_v1_notifications_get",
    # "unread_count_api_v1_notifications_unread_count_get",
]