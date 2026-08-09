# AI-miniSOC MCP Server

把 FastAPI 后端包装成 MCP（Model Context Protocol）服务，让 AI Agent 通过标准化协议调用 SOC 能力。

## 架构：纯 C 路线（手写 27 个 tools）

| 部分 | 来源 | tools 数 | 端点 |
|------|------|---------|------|
| **C**（手写精选）| `app/mcp/tools/*.py` | 27 | `GET http://localhost:8100/sse` (SSE transport) |

**为什么不用 B（fastapi-mcp 自动 OpenAPI → MCP）**：

1. Agent 实际只用 OpenAPI 142 个路由中的 7 个（资产/字典相关），剩下都是后台管理（用户/角色/菜单/部门/审计/通知），对 SOC 工作流无价值
2. fastapi-mcp 依赖脆弱（OpenAPI 自引用递归 + Server API 版本不兼容，需要打库源码补丁 + monkey-patch）
3. 全 C tool 名字短（5-20 字符），B 名字长（30+ 字符），Agent 上下文省 ~70%
4. Token 管理全自动（C 用 TokenManager 后台续期，B 必须每次带 Authorization）
5. 写操作可控（C 可直连 DB 绕过前端 schema bug）

如未来需要重新启用 B（自动从新增 OpenAPI endpoint 同步 tool），代码备份见 `app/mcp/server.py` 底部注释块 + 备份白名单 `SAFE_OPENAPI_OPS_DISABLED`。

## 启动

后端启动时自动拉起 MCP（无需额外进程）：

```bash
cd src/backend
/Users/xiejava/AIProject/AI-miniSOC/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

启动日志会看到：
```
[INFO] app.mcp.server: MCP-C: 手写 tools (27 个): [...]
[INFO] app.mcp.server: MCP SSE server starting on http://0.0.0.0:8100/sse (SSE transport)
```

## MCP 端点

| 端点 | 协议 | 用途 |
|------|------|------|
| `http://localhost:8100/sse` | SSE | MCP 客户端连接（拿到 session_id） |
| `http://localhost:8100/messages/?session_id=...` | POST JSON-RPC | 发送 MCP 请求 |

## MCP 客户端配置

```json
{
  "mcpServers": {
    "ai-mini-soc": {
      "url": "http://localhost:8100/sse",
      "transport": "sse"
    }
  }
}
```

## 工具清单（27 个，全部按 SOC 工作流精选）

### 0. 系统 / Token 管理（3）
| Tool | 鉴权 | 说明 |
|------|------|------|
| `get_system_info` | ❌ 免鉴权 | SOC 元信息（应用名 / Logo / 版权 / 描述），Agent 启动时调用 |
| `set_mcp_credentials(username, password)` | — | 配置账号密码 + 后台线程自动刷新 JWT |
| `get_token_status` | — | 查询 token 状态（剩余有效期、是否配置） |

### 1. 认证（3）
| Tool | 鉴权 | 说明 |
|------|------|------|
| `login(username, password)` | ❌ | 直接登录拿 token（不走 TokenManager） |
| `get_current_user` | ✅ | 当前登录用户 |
| `logout` | ✅ | 撤销当前 token |

### 2. 资产（6）
| Tool | 鉴权 | 说明 |
|------|------|------|
| `list_assets` | ✅ | 资产列表，按 IP/名称/类型/重要等级/状态/网络区域/数据源过滤 |
| `get_asset(asset_id)` | ✅ | 资产详情 |
| `get_asset_summary(asset_id)` | ✅ | 单资产汇总 |
| `list_asset_ports(asset_id)` | ✅ | 资产的端口列表（攻击面分析） |
| `get_asset_sources(asset_id)` | ✅ | 资产的数据源（溯源） |
| `get_asset_overview()` | ✅ | 全局资产 KPI（95 资产 / 9 高危等） |

### 3. 告警（3）
| Tool | 鉴权 | 说明 |
|------|------|------|
| `list_alerts` | ✅ | Wazuh 告警列表，按 level/agent_id/ip/时间窗口过滤 |
| `get_alert_detail(alert_id)` | ✅ | 告警详情 |
| `get_alert_stats` | ✅ | 告警统计 |

### 4. 事件（3）
| Tool | 鉴权 | 说明 |
|------|------|------|
| `list_incidents` | ✅ | 事件列表，按 status/severity 过滤 |
| `get_incident(incident_id)` | ✅ | 事件详情 |
| `create_incident` | ✅ | 创建事件（**直连 DB**绕过前端 IncidentCreate schema bug） |

### 5. 字典（3）
| Tool | 鉴权 | 说明 |
|------|------|------|
| `list_dicts(page, page_size, search, dict_type)` | ✅ | 字典列表（分页） |
| `list_dict_types()` | ✅ | 所有字典类型名（`asset_criticality` 等） |
| `get_dicts_by_type(dict_type)` | ✅ | 按类型查字典项（如 `alert_level` 的所有级别定义） |

### 6. AI 分析（3）
| Tool | 鉴权 | 说明 |
|------|------|------|
| `ai_analyze_alert` | ✅ | 用智谱 AI 解释告警（含 risk_assessment） |
| `ai_explain_log` | ✅ | 解释一段原始日志 |
| `get_ai_analysis` | ✅ | 取缓存的分析结果 |

### 7. Loki 直连（3）
| Tool | 鉴权 | 说明 |
|------|------|------|
| `loki_query_range(query, hours, limit)` | ❌ | 直连 Loki API，按 LogQL 查日志 |
| `loki_list_labels` | ❌ | 列出所有 label |
| `loki_label_values(label)` | ❌ | 查某 label 取值 |

## Token 自动刷新机制

`TokenManager`（`app/mcp/token_manager.py`）：

- 启动时调用 `set_mcp_credentials`，用账号密码登录一次拿 access + refresh
- 后台线程每分钟检查，**access 过期前 5 分钟**自动用 refresh 换新 token
- refresh 也过期 → 自动重新登录（用最初凭证）
- 完全凭证失效（密码改 / 账号锁）→ 抛 `TokenExpiredError`，提示 Agent 调用 `set_mcp_credentials` 重新配置
- 进程退出时后台线程自动清理

**Agent 只需调一次 `set_mcp_credentials`，后续所有工具自动复用**——无需关心 token 生命周期。

## 推荐 Agent 调用流程

```
1. get_system_info              # 自我介绍，问账号密码
2. set_mcp_credentials(u, p)    # 一次性配置
3. get_token_status             # 确认就绪
4. list_assets / list_alerts    # 探索 SOC
5. get_asset_overview           # 全局 KPI（无参数）
6. ai_analyze_alert             # AI 解释威胁
7. loki_query_range             # 看原始日志
8. create_incident              # 落库
```

## 手动测试

```bash
/Users/xiejava/AIProject/AI-miniSOC/venv/bin/python /tmp/test_full_c.py
```

完整端到端测试：登录 + 调6 个新 tool。

## 已知限制

1. **create_incident 直连 DB** — 因 `IncidentCreate` schema 漏 `status/created_by` 字段；
   若修复该 schema，可改回 `call_api("POST", "/incidents/")`
2. **SSE 端口 8100** — 与主服务 8000 分离；多机部署需在 `app/mcp/server.py` 改端口
3. **in-memory TokenManager** — 单进程可用；多实例需切 Redis
4. **FastMCP SSE 单 worker** — 高并发场景需切 streamable HTTP（mcp 2.0+ 支持）

## 文件清单

```
src/backend/app/mcp/
├── __init__.py            # mount_mcp 导出
├── server.py              # FastMCP 装配 + SSE server 后台线程（含 B 部分历史备份）
├── token_manager.py       # JWT 自动刷新（单例）
├── README.md              # 本文件
└── tools/
    ├── __init__.py        # register_all
    ├── base.py            # call_api() 共享 HTTP 客户端
    ├── system_tools.py    # get_system_info / set_mcp_credentials / get_token_status
    ├── auth_tools.py      # login / logout / get_current_user
    ├── asset_tools.py     # list_assets / get_asset / get_asset_summary
    ├── asset_extra_tools.py  # list_asset_ports / get_asset_overview / get_asset_sources
    ├── alert_tools.py     # list_alerts / get_alert_detail / get_alert_stats
    ├── incident_tools.py  # list_incidents / get_incident / create_incident
    ├── ai_tools.py        # ai_analyze_alert / ai_explain_log / get_ai_analysis
    ├── dict_tools.py      # list_dicts / list_dict_types / get_dicts_by_type
    └── loki_tools.py      # loki_query_range / loki_list_labels / loki_label_values
```