# AI-miniSOC Pi Agent 集成架构设计

> 版本: v1.0
> 日期: 2026-06-15
> 状态: 设计评审通过，待开发实施
> 关联项目: [pi.dev](https://pi.dev) / [earendil-works/pi](https://github.com/earendil-works/pi)

---

## 1. 背景与目标

### 1.1 当前 AI 集成现状

| 组件 | 现状 | 局限 |
|------|------|------|
| **告警分析** | `app/services/ai_analysis.py` 调 `zhipuai` SDK | 单 Provider（GLM），无工具调用，无多轮记忆 |
| **Art Bot 聊天** | `app/services/chat_service.py` 通过 `claude` CLI subprocess | 依赖本地 CLI，运维脆弱，无多模型切换 |
| **数据源** | 智谱 API + Anthropic Claude（CLI） | 两套独立链路，无法统一管控 |
| **能力** | 单轮 prompt | 无 Skill、无 MCP、无 Multi-Agent |

### 1.2 目标

1. **统一 AI Agent 底座**：用 Pi（@earendil-works/pi-agent-core + pi-ai）作为运行时，替换现有两套 AI 集成
2. **多模型可热切换**：GLM / Claude / OpenAI / DeepSeek 在系统设置中一键切换
3. **Agent 能力完备**：工具调用 / Skill 系统 / MCP 协议 / Multi-Agent / 三层记忆
4. **生产级可观测**：复用现有 Loki + Grafana，全链路 Trace
5. **安全可控**：写工具（封 IP / 加白名单）走 human-in-the-loop 审核

### 1.3 设计原则

- **Python 主、Node 辅**：业务逻辑保留在 FastAPI，Node 仅做 Agent 运行时
- **进程隔离**：每个 Agent = 1 个 Node 子进程，崩溃不污染主服务
- **业务真理源唯一**：写工具在 FastAPI 端执行，Node 只做反向 HTTP 调用
- **可观测先行**：所有 LLM/工具调用带 trace_id，全部送 Loki
- **渐进式落地**：分 5 个阶段（详见 §6），每个阶段独立可交付

---

## 2. 整体架构

```
┌──────────────────────────────────────────────────────────────────┐
│                 Vue3 Frontend (Art Design Pro)                    │
│   告警详情页 / Art Bot 聊天 / 系统设置 / Multi-Agent 编排编辑器      │
└──────────────────────┬───────────────────────────────────────────┘
                       │ REST + SSE
┌──────────────────────▼──────────────────────────────────────────┐
│              FastAPI Backend (Python 3.13)                        │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  /api/v1/ai/* (新/改造)                                      │ │
│  │  · /analyze-alert  /explain  /chat (SSE)                     │ │
│  │  · /skills  /mcp-servers  /agents  /workflows               │ │
│  │  · /memories  /models                                       │ │
│  └─────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │AgentProcessManager│ │MemoryStore       │  │MCP Gateway      │  │
│  │· 子进程池         │  │· soc_agent_mem..│  │· 外部 MCP 客户端 │  │
│  │· JSON-RPC stdio  │  │· 会话/实体/知识  │  │· 健康检查        │  │
│  │· 心跳+重启        │  │· RAG-lite        │  │· 工具注册        │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  Observability: Prometheus Metrics + JSON Logs (Promtail)   │ │
│  └─────────────────────────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────────────────────────┘
                       │ JSON-RPC (over stdio)
┌──────────────────────▼──────────────────────────────────────────┐
│           pi-agent-runner.js (Node.js 进程池)                     │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  @earendil-works/pi-agent-core (Agent runtime)                │ │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐               │ │
│  │  │ Skills  │ │ Tools   │ │ Events  │ │Sessions │               │ │
│  │  │Registry │ │ Loader  │ │ Stream  │ │持久化    │               │ │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────┘               │ │
│  │  @earendil-works/pi-ai (LLM 统一适配)                         │ │
│  └─────────────────────────────────────────────────────────────┘ │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ SOC 工具集        │  │ 内部 HTTP 客户端  │  │ MCP 客户端       │  │
│  │ (反向调 FastAPI) │  │ (→ FastAPI)    │  │ (→ 外部 MCP)    │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTPS
┌──────────────────────▼──────────────────────────────────────────┐
│         LLM Providers: GLM / Claude / OpenAI / DeepSeek           │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. 核心设计

### 3.1 JSON-RPC 协议

每条消息一行 JSON（`\n` 分隔），对齐 Pi 自身的 RPC 模式。

#### 请求（FastAPI → Node）

```json
{ "id": "req-001", "method": "agent.prompt", "params": {
    "sessionId": "uuid-xxx",
    "userMessage": "分析 192.168.0.5 上的告警",
    "model": "anthropic/claude-sonnet-4-5",
    "skills": ["alert-triage", "log-search"],
    "tools": ["query_assets", "query_alerts"],
    "systemPromptOverride": "..."
}}
```

支持的 method：
- `agent.prompt` — 发起对话
- `agent.continue` — 继续已有 session
- `agent.abort` — 中断运行
- `agent.list_tools` — 列出可用工具
- `agent.reload_skills` — 热加载新 skill

#### 事件流（Node → FastAPI，特殊 id = "evt"）

```json
{ "id": "evt", "method": "agent.event", "params": {
    "sessionId": "uuid-xxx",
    "type": "text_delta",
    "delta": "正在查询 192.168.0.5 的资产...",
    "ts": 1718420000000,
    "trace_id": "...",
    "span_id": "..."
}}
```

#### 事件类型映射

| Pi 原生事件 | 转发到 SSE | 用途 |
|------------|----------|------|
| `text_delta` | ✅ `{delta: "..."}` | 流式 token |
| `tool_execution_start/end` | ✅ `{tool, status}` | 工具调用追踪 |
| `message_end` | ✅（内部） | 消息落库 |
| `turn_end` | ✅ | 一轮结束 |
| `agent_end` | ✅ `[DONE]` | session 结束 |
| `error` | ✅ `{error}` | 异常 |

### 3.2 进程管理

```python
class AgentProcess:
    session_id: str
    role: str  # "alert-triage" / "chat" / "report-writer" / ...
    proc: subprocess.Popen
    stdin_writer: asyncio.StreamWriter
    stdout_reader: asyncio.StreamReader
    pending_requests: Dict[str, asyncio.Future]
    last_heartbeat: float
    state: Literal["idle", "running", "dead"]
```

**配置**：
- `command`: `["node", "pi-agent-runner.js", "--stdio", "--config", "/etc/pi/config.json"]`
- `cwd`: `/opt/ai-minisoc/agent-runner`
- `idle_timeout`: 1800s（30 分钟无活动自杀）
- `max_lifetime`: 7200s（2 小时强制重启，防内存泄露）
- `max_concurrent`: 50（进程池上限）

**复用策略**：
- 同一 `sessionId` 永远绑同一进程（多轮对话持久）
- 进程空闲 30 分钟 → 优雅退出，session 数据序列化到 DB
- 下次同 sessionId 复活 → 从 DB 加载历史 → 恢复

### 3.3 工具调用回路

```typescript
// Node 端（pi-agent-runner.js）
{
  name: "query_assets",
  parameters: Type.Object({ ip: Type.Optional(Type.String()) }),
  execute: async (args, ctx) => {
    const res = await fetch("http://127.0.0.1:8000/internal/tools/query_assets", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Service-Token": process.env.INTERNAL_SERVICE_TOKEN,
        "X-Trace-Id": ctx.trace_id
      },
      body: JSON.stringify(args)
    });
    if (!res.ok) throw new Error(`tool call failed: ${res.status}`);
    return await res.json();
  }
}
```

```python
# FastAPI 端（src/backend/app/api/internal/tools.py）
@router.post("/tools/{tool_name}")
async def invoke_tool(
    tool_name: str,
    request: Request,
    _: None = Depends(verify_service_token),
    db: Session = Depends(get_db)
):
    body = await request.json()
    trace = get_trace_from_header(request)
    span = trace.start_span(f"tool.{tool_name}")

    tool = TOOL_REGISTRY.get(tool_name)
    if not tool:
        raise HTTPException(404, f"tool {tool_name} not registered")

    try:
        result = await tool.execute(db=db, user=ctx.user, **body)
        span.set_attribute("status", "ok")
        tool_execution_count.labels(tool=tool_name, status="ok").inc()
        return {"ok": True, "data": result}
    except Exception as e:
        span.record_exception(e)
        tool_execution_count.labels(tool=tool_name, status="error").inc()
        return {"ok": False, "error": str(e)}
    finally:
        span.end()
```

**安全边界**：
- `X-Service-Token` 从环境变量读取，Node 进程启动时注入
- 只监听 `127.0.0.1:8000`，或用独立端口
- 写工具默认禁用，需 `enabled_write_tools=true` 配置

### 3.4 Skill 系统

```
soc-skills/                              # 项目本地 skill 仓库
├── alert-triage/                        # 告警研判
│   ├── SKILL.md                         # YAML frontmatter + 描述
│   ├── instructions.md                  # 详细指令（按需加载）
│   ├── tools/                           # skill 专属工具
│   │   ├── query_alerts.py
│   │   └── get_wazuh_rule.py
│   └── examples/
│       └── ssh-bruteforce.md
├── log-search/                          # 日志检索
├── incident-report/                     # 事件报告生成
├── threat-intel/                        # 威胁情报查询
└── response-playbook/                   # 响应剧本执行
```

**SKILL.md 示例**：

```markdown
---
name: alert-triage
description: |
  研判 Wazuh 告警：评估风险等级、识别误报、给出处置建议。
  适用场景：用户询问告警、要求分析日志、要求威胁评估。
allowed-tools: query_alerts, get_wazuh_rule, query_assets, search_logs
---

# 告警研判技能

## 工作流程
1. 拉取告警上下文（rule、agent、原始日志）
2. 查询资产信息（确认资产类型、暴露面、责任人）
3. 检索近期日志（寻找关联事件）
4. 评估风险等级（结合 Wazuh 规则级别 + 业务影响）
5. 输出研判结论
```

**三层加载策略**（防 prompt 爆炸）：

| Layer | 内容 | Token 占用 | 加载时机 |
|-------|------|-----------|---------|
| 1 | Skill 名称 + 描述 | ~50 / skill | 启动时常驻 |
| 2 | Skill 详细指令 | ~500-2000 | 触发时按需 |
| 3 | Skill 工具 schema | ~100-300 / 工具 | 注册到 agent |

**DB 表**：

```python
class SOCSkill(Base):
    __tablename__ = "soc_agent_skills"
    id, name, description, allowed_tools (JSONB),
    enabled, source (git/s3/local), version, updated_at
```

**CRUD 端点**：
- `GET /api/v1/ai/skills` — 列出所有 skill
- `GET /api/v1/ai/skills/{name}` — 详情
- `POST /api/v1/ai/skills/{name}/sync` — 同步
- `POST /api/v1/ai/skills/{name}/toggle` — 启停
- `GET /api/v1/ai/skills/{name}/logs` — 使用统计

### 3.5 MCP Gateway

```
┌──────────────────────────────────────────────────────────┐
│              MCP Gateway (FastAPI 端)                     │
│  · 维护 MCP server 连接池                                  │
│  · 把 MCP 工具注册为 SOC 内部工具 (mcp_ 前缀)               │
│  · 协议转换：MCP JSON-RPC ↔ FastAPI 内部 HTTP              │
└──────────────────┬───────────────────────────────────────┘
                   │
        ┌──────────┼──────────┬─────────────┐
        ▼          ▼          ▼             ▼
   ┌────────┐ ┌────────┐ ┌─────────┐  ┌──────────┐
   │ Threat │ │ 资产库  │ │ VirusTotal│  │ 自定义 MCP│
   │ Intel  │ │ MCP    │ │ MCP      │  │ (公司内部)│
   └────────┘ └────────┘ └─────────┘  └──────────┘
```

**DB 表**：

```python
class MCPServer(Base):
    __tablename__ = "soc_mcp_servers"
    id, name, transport (stdio/http/websocket),
    command, args, env, url, headers,
    enabled, health_check_url, last_health_at, last_health_status
```

**启动流程**：

```python
async def bootstrap_mcp():
    for server in mcp_servers:
        tools = await mcp_client.list_tools(server)
        for tool in tools:
            TOOL_REGISTRY[f"mcp_{server.name}_{tool.name}"] = MCPToolWrapper(
                server=server, tool=tool
            )
        asyncio.create_task(health_check_loop(server))  # 60s 一次
```

**安全约束**：
- MCP server 配置必须由管理员写入（普通用户只读）
- 连接超时 / 重连在 Gateway 层处理
- MCP 调用结果过 PII 过滤层（防 token 泄露给 LLM）

### 3.6 工具集

#### 第一期 MVP 工具

| 工具 | 类型 | 描述 | 写? |
|------|------|------|-----|
| `query_assets` | 只读 | 资产查询（按 IP/名称/部门） | ❌ |
| `query_alerts` | 只读 | 告警查询（按主机/级别/时间） | ❌ |
| `search_logs` | 只读 | Loki 日志检索 | ❌ |
| `get_wazuh_rule` | 只读 | 查询 Wazuh 规则详情 | ❌ |
| `correlate_events` | 只读 | 同一 IP/资产的多源事件关联 | ❌ |
| `list_assets_for_ip` | 只读 | 反查某 IP 对应资产 | ❌ |
| `block_ip` | **写** | 封禁 IP | ⚠️ |
| `add_to_whitelist` | **写** | 加入白名单 | ⚠️ |
| `trigger_resync` | **写** | 触发资产重新采集 | ⚠️ |

#### 写工具的二次确认

```python
class BlockIPTool:
    requires_role = "admin"
    requires_approval = True  # human-in-the-loop

    async def execute(self, db, ip: str, duration_minutes: int, reason: str, ctx):
        # 1. 写 pending 决策
        decision = SOCPendingDecision(
            type="block_ip",
            payload={"ip": ip, "duration": duration_minutes, "reason": reason},
            requested_by=ctx.user_id,
            trace_id=ctx.trace_id,
            status="pending"
        )
        db.add(decision)
        db.commit()

        # 2. WebSocket 推送给管理员
        await ws_manager.send_to_admins({
            "type": "pending_decision",
            "id": str(decision.id),
            "title": f"AI 请求封禁 {ip}",
            "payload": decision.payload
        })

        # 3. 返回"等待审核"给 LLM
        return {"status": "pending_approval", "decision_id": str(decision.id)}
```

### 3.7 三层记忆

```python
# 复用：soc_chat_messages (已有)
class AgentShortTermMemory:
    __tablename__ = "soc_chat_messages"  # 已有

# 新增
class AgentEntityMemory(Base):
    """实体级长期记忆：每个 IP/资产/规则的历史研判"""
    __tablename__ = "soc_agent_entity_memories"
    id, entity_type (ip/asset/rule/incident), entity_key,
    memory_type (verdict/risk/note), content, confidence,
    source_session_id, created_at, expires_at, version

class AgentSharedMemory(Base):
    """跨会话知识：multi-agent 共享上下文"""
    __tablename__ = "soc_agent_shared_memories"
    id, scope (incident_id/case_id), key, value (JSONB),
    updated_by_agent, updated_at, ttl
```

**自动记忆写入**：

```python
async def extract_entity_memories(verdict: dict, ctx: AgentContext):
    if verdict.get("verdict") == "true_positive":
        for ip in verdict.get("related_ips", []):
            memory = AgentEntityMemory(
                entity_type="ip", entity_key=ip,
                memory_type="verdict",
                content=f"{verdict['risk_level']}: {verdict['explanation'][:200]}",
                source_session_id=ctx.session_id,
                expires_at=datetime.utcnow() + timedelta(days=90)
            )
            db.add(memory)
```

**注入策略**：
- **会话开始**：自动加载 `soc_chat_messages` 历史
- **查询某实体**：检索 `soc_agent_entity_memories` 最近 N 条
- **Multi-Agent 协作**：所有 agent 共享 `soc_agent_shared_memories` 同 scope

### 3.8 Multi-Agent 编排

#### 模式 A：Role-based（基础）

```python
class SOCAgentRole(Base):
    __tablename__ = "soc_agent_roles"
    id, role_id (unique), display_name, description,
    default_provider, default_model,
    system_prompt, enabled_skills (JSONB), enabled_tools (JSONB),
    enabled, max_concurrent, created_at
```

| 角色 | 模型 | Skill | 工具 |
|------|------|-------|------|
| `alert-triage` | claude-sonnet-4-5 | alert-triage, threat-intel | query_alerts, query_assets, search_logs, get_wazuh_rule, correlate_events |
| `incident-investigator` | claude-sonnet-4-5 | log-search, threat-intel, alert-triage | 全部只读 |
| `report-writer` | glm-4-plus | incident-report | query_alerts, query_incidents |
| `chat-assistant` | glm-4-flash | (无) | 全部只读 |
| `responder` | claude-sonnet-4-5 | response-playbook | 写工具（需审核） |

#### 模式 B：Pipeline（DAG 编排）

```yaml
id: critical-alert-response-v1
name: 严重告警响应工作流
trigger: rule_level >= 12
steps:
  - id: triage
    agent: alert-triage
    input: ${trigger.alert}
    output: triage_result
    timeout: 60s

  - id: investigate
    agent: incident-investigator
    input: ${trigger.alert}
    output: investigation
    depends_on: [triage]
    parallel_with: [enrich]
    timeout: 90s

  - id: enrich
    agent: threat-intel-enricher
    input: ${trigger.alert.src_ip}
    output: threat_intel
    depends_on: [triage]
    timeout: 30s

  - id: report
    agent: report-writer
    input: ${triage} + ${investigation} + ${threat_intel}
    output: report
    depends_on: [investigate, enrich]
    timeout: 120s

  - id: notify
    type: action
    action: send_notification
    input: ${report}
    depends_on: [report]
```

**执行器**：

```python
class AgentOrchestrator:
    async def run_role(self, role_id: str, input: dict) -> dict:
        role = self.get_role(role_id)
        session = self.create_session(role_id=role_id, role_config=role)
        return await self.agent_manager.prompt(session, input)

    async def run_pipeline(self, workflow_id: str, trigger: dict) -> dict:
        wf = self.get_workflow(workflow_id)
        order = topo_sort_layers(wf.steps)  # 按层分组
        results = {}
        for layer in order:
            await asyncio.gather(*[
                self._run_step(step, trigger, results) for step in layer
            ])
        return results
```

**Agent 间通信**通过 `soc_agent_shared_memories` 共享上下文，避免进程间直接通信。

### 3.9 可观测性

#### 监控分层

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Metrics (Prometheus 抓取 → Grafana 仪表板)        │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Structured Logs (stdout JSON → Promtail → Loki)   │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Traces (trace_id 贯穿全链路 → Loki 关联查询)       │
└─────────────────────────────────────────────────────────────┘
```

#### 关键 Metrics

```python
llm_request_duration = Histogram(
    "llm_request_duration_seconds", "LLM 请求延迟",
    ["model", "provider", "status"]
)
llm_tokens_total = Counter(
    "llm_tokens_total", "Token 消耗",
    ["model", "direction"]  # input / output
)
llm_cost_usd = Counter(
    "llm_cost_usd_total", "累计成本", ["model", "provider"]
)
tool_execution_count = Counter(
    "tool_execution_count", "工具调用次数", ["tool", "status"]
)
agent_process_count = Gauge(
    "agent_process_count", "活跃 Agent 进程", ["role", "state"]
)
agent_session_active = Gauge(
    "agent_session_active", "活跃会话数", ["role"]
)
```

#### LLM Trace（Node 端）

```typescript
async function tracedStream(model, context, traceId) {
  const spanId = uuid();
  const start = Date.now();
  try {
    const stream = stream(model, context);
    let inputTokens = 0, outputTokens = 0;
    for await (const event of stream) {
      if (event.type === "usage") {
        inputTokens = event.usage.input;
        outputTokens = event.usage.output;
      }
      yield event;
    }
    emit({ type: "trace.llm", trace_id: traceId, span_id: spanId,
           model: model.id, provider: model.provider,
           duration_ms: Date.now() - start,
           input_tokens: inputTokens, output_tokens: outputTokens,
           cost_usd: calculateCost(model.id, inputTokens, outputTokens),
           status: "ok" });
  } catch (e) {
    emit({ type: "trace.llm", trace_id: traceId, span_id: spanId,
           status: "error", error: e.message });
    throw e;
  }
}
```

#### 工具 Trace（FastAPI 端）

```python
@router.post("/tools/{tool_name}")
async def invoke_tool(tool_name, request, db, trace: TraceContext = Depends(...)):
    span = trace.start_span(f"tool.{tool_name}")
    start = time.time()
    try:
        result = await tool.execute(db=db, **body)
        span.set_attribute("status", "ok")
        tool_execution_count.labels(tool=tool_name, status="ok").inc()
        return {"ok": True, "data": result}
    except Exception as e:
        span.record_exception(e)
        tool_execution_count.labels(tool=tool_name, status="error").inc()
        return {"ok": False, "error": str(e)}
    finally:
        duration = time.time() - start
        logger.info("tool_execution",
            extra={"tool": tool_name, "duration_ms": duration*1000,
                   "trace_id": trace.trace_id, "status": span.status})
        span.end()
```

#### Grafana 仪表板（复用现有栈）

| 仪表板 | 关键面板 |
|--------|---------|
| **Agent Overview** | 活跃进程 / 活跃会话 / Token 速率 / 成本速率 |
| **LLM Performance** | P50/P95/P99 延迟 / 各模型对比 / 错误率 / Token 分布 |
| **Tool Usage** | 工具 Top 10 / 慢工具 / 错误工具 |
| **Trace Explorer** | 按 trace_id 查完整调用链 |

---

## 4. 数据流（一次告警研判）

```
1. 前端：用户点"AI 分析"
   POST /api/v1/ai/analyze-alert { alert_id }
   携带: Authorization + trace_id

2. FastAPI:
   a) 查询 alert 基本信息
   b) 查缓存 (soc_ai_analyses)
   c) 命中 → 直接返回
   d) 未命中 → 继续

3. FastAPI → AgentProcessManager
   a) 查 session (按 alert_id 复用)
   b) 不存在 → spawn(role="alert-triage") → 启动 pi-agent-runner.js
   c) 存在 → 复用进程
   d) JSON-RPC: agent.prompt(sessionId, message, skills=["alert-triage"])

4. pi-agent-runner.js (Node):
   a) 加载 system_prompt (含 skill 描述)
   b) 调 LLM → 返回 tool_call
   c) 执行 query_assets({ip: "192.168.0.5"})
      → HTTP POST localhost:8000/internal/tools/query_assets
   d) 工具结果喂回 LLM
   e) 调 search_logs(...)
   f) 重复 b-e，直到 LLM 输出结论

5. 事件流 (SSE) 推给前端:
   - text_delta / tool_execution_start / tool_execution_end / agent_end

6. FastAPI 后处理:
   a) 解析最终输出 → 提取 verdict/risk/recommendations
   b) 写 soc_ai_analyses (7天缓存)
   c) 提取 entity memory → 写 soc_agent_entity_memories
   d) 写 audit_log
   e) 返回 JSON

7. 前端：流式渲染 + 最终保存
```

---

## 5. 部署架构

```
┌─────────────────────────────────────────────────────────────┐
│  Production Server (192.168.0.42)                            │
│                                                              │
│  ┌────────────────────────────────────────────┐              │
│  │  Caddy / Nginx                              │              │
│  │  - 前端静态文件                              │              │
│  │  - /api/* → FastAPI 反代                    │              │
│  └────────────┬───────────────────────────────┘              │
│               │                                                │
│  ┌────────────▼───────────────────────────────┐              │
│  │  FastAPI (uvicorn) :8000                    │              │
│  │  + AgentProcessManager (in-process)         │              │
│  └────────────┬───────────────────────────────┘              │
│               │ subprocess                                     │
│  ┌────────────▼───────────────────────────────┐              │
│  │  pi-agent-runner.js × N (1-50)              │              │
│  │  cwd: /opt/ai-minisoc/agent-runner          │              │
│  └────────────────────────────────────────────┘              │
│                                                              │
│  Promtail → Loki (复用)                                       │
│  Prometheus → Grafana (复用)                                  │
└─────────────────────────────────────────────────────────────┘
```

**Node.js 安装**：
- 系统装 Node 20.x LTS
- 路径 `/opt/ai-minisoc/agent-runner/`
- 依赖 `npm install --ignore-scripts @earendil-works/pi-agent-core @earendil-works/pi-ai`
- 配置 `/etc/ai-minisoc/agent-runner.json`（provider keys、service token）

---

## 6. 实施路线图

| 阶段 | 周期 | 交付物 |
|------|------|--------|
| **POC** | 1 周 | spawn Node 进程 + JSON-RPC ping/pong + 1 次 LLM 调通 + Grafana 看到 1 次调用 |
| **MVP-1** | 2 周 | 告警分析跑通：alert-triage 角色 + 3 个只读工具 + 缓存 + SSE + 审计 |
| **MVP-2** | 2 周 | Skill 系统 + 工具集全实现 + Art Bot 切到 Pi（替换 Claude CLI） |
| **Beta** | 2 周 | MCP Gateway + 实体记忆 + 1 个 Pipeline 范例 |
| **GA** | 2 周 | 写工具 + Human-in-the-loop + Grafana 仪表板 + 文档 |

---

## 7. 测试策略

| 层 | 工具 | 覆盖 |
|----|------|------|
| **单元** | pytest | 工具实现、prompt 构造、记忆写入、SQL/JSON 解析 |
| **集成** | pytest + httpx | FastAPI 内部端点、JSON-RPC 桩、缓存 |
| **Node 桩** | vitest | 工具 schema、JSON-RPC 解析 |
| **E2E (mock LLM)** | pytest + mock | FastAPI ↔ Node ↔ mock LLM 完整流程 |
| **E2E (real LLM)** | pytest + 小模型 | 真实 GLM-Flash，验证 prompt 质量 |
| **可观测性** | prometheus_client | 指标正确性 |

**Mock LLM 服务**用于集成测试，返回预设响应（tool_call + text_delta 序列），不依赖真实 LLM API。

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解 |
|------|------|------|
| **Node 内存泄露** | 长时间运行崩溃 | `max_lifetime=2h` 强制重启 + 监控进程 RSS |
| **LLM 成本失控** | 月底账单爆炸 | 限流（每用户/每 session tokens）、预算告警、模型分级 |
| **Agent 死循环** | 工具反复调用 | `max_iterations=20` 硬限制 + 单 step 60s timeout |
| **MCP server 故障** | agent 卡住 | 独立超时（10s）+ 失败降级 |
| **写工具误操作** | 误封 IP/误改白名单 | Human-in-the-loop + 审计 + 二次确认 UI |
| **敏感数据泄露** | token/密钥送给 LLM | PII 过滤层 + 提示词禁传敏感字段 |
| **Pi 升级 breaking** | 集成崩溃 | 锁定 pi-agent-core 版本 + 升级前 staging 验证 |
| **进程池打满** | 新请求 503 | 队列上限 + 排队超时 + Grafana 告警 |

---

## 9. 待办（设计层面未决）

- [ ] Pi 私有模型接入（如公司内部 LLM）— 需评估 OpenAI 兼容接口适配
- [ ] LLM 输出 PII 过滤层具体规则
- [ ] Multi-Agent 工作流可视化编辑器（YAML → DAG UI）
- [ ] Skill 仓库是 Git 还是 S3 / 对象存储

---

## 10. 关联文档

- 当前 AI 实现：`src/backend/app/services/ai_analysis.py`、`src/backend/app/services/chat_service.py`
- 配置项：`src/backend/app/core/config.py`（GLM_* 已有，扩展 PI_* 命名空间）
- 现有监控栈：Wazuh + Loki + Grafana（CLAUDE.md 已有说明）
- 采集器架构：`docs/design/2026-06-07-collector-integration-architecture.md`（可作为进程管理参考）

---

**版本**: v1.0
**最后更新**: 2026-06-15
**下一步**: 实施路线图 §6 阶段 1 - POC
