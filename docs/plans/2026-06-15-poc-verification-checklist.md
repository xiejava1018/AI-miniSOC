# Pi Agent POC 验证清单

> 版本: v1.0
> 日期: 2026-06-15
> 状态: 待执行
> 关联设计: [2026-06-15-pi-ai-integration-design.md](./2026-06-15-pi-ai-integration-design.md)

---

## 概述

本文档定义 Pi Agent POC 阶段的 5 个验收点，对应设计文档 §6 实施路线图第一阶段目标。

**POC 阶段目标**: spawn Node 进程 + JSON-RPC ping/pong + 1 次 LLM 调通 + Grafana 看到 1 次调用

---

## 验收点清单

| # | 验收点 | 检查方法 | 预期结果 | 失败处理 |
|---|--------|----------|----------|----------|
| 1 | Node 进程被 spawn | `pgrep -f pi-agent-runner` 或 `ps aux \| grep pi-agent` | 至少 1 个 `pi-agent-runner` 进程运行 (PID 可见) | 检查 AgentProcessManager 是否正确 spawn，查看后端日志 |
| 2 | JSON-RPC ping/pong 通 | `POST /api/v1/ai/agent/prompt` 发送 `agent.list_tools` | 返回包含 `tools` 数组的 JSON-RPC 响应 | 验证 Node 进程 stdio 通信，检查 `X-Internal-Service-Token` |
| 3 | 1 次 LLM 调用成功 | `POST /api/v1/ai/agent/prompt` 发送 `agent.prompt` | SSE/响应包含 `text_delta` 事件 | 检查 `PI_PROVIDER_API_KEY` 配置，查看 Node 进程日志 |
| 4 | Prometheus 看到指标 | `curl http://localhost:8000/metrics` | 包含 `llm_request_duration_seconds` 指标 | 确认 `prometheus_client` 已注册指标，先触发 1 次 LLM 调用 |
| 5 | Loki 看到结构化日志 | Loki 查询 `{job="ai-minisoc"}` | 包含 `trace_id` 字段的 JSON 行 | 确认 Promtail 配置正确，检查 Loki 连接，检查日志格式 |

---

## 验收点详情

### VP-1: Node 进程被 spawn

#### 检查方法

**方式 A (推荐)**:
```bash
pgrep -f "pi-agent-runner"
```

**方式 B (macOS 兼容)**:
```bash
ps aux | grep -E "pi-agent|node" | grep -v grep
```

#### 预期结果

- 至少 1 个 `pi-agent-runner` 进程运行
- 进程 PID 可获取
- 进程状态为 running/idle

#### 失败处理

1. **检查后端日志**
   ```bash
   # 查看 uvicorn 日志
   tail -f src/backend/logs/*.log
   ```

2. **检查 AgentProcessManager 初始化**
   - 确认 `pi-agent-runner.js` 存在于 `/opt/ai-minisoc/agent-runner/`
   - 确认 Node 依赖已安装: `npm list @earendil-works/pi-agent-core`

3. **手动启动 Node 进程调试**
   ```bash
   cd /opt/ai-minisoc/agent-runner
   node pi-agent-runner.js --stdio --config /etc/pi/config.json 2>&1
   ```

---

### VP-2: JSON-RPC ping/pong 通

#### 检查方法

```bash
curl -X POST http://localhost:8000/api/v1/ai/agent/prompt \
  -H "Content-Type: application/json" \
  -H "X-Trace-Id: poc-test-$(date +%s)" \
  -d '{
    "id": "test-001",
    "method": "agent.list_tools",
    "params": {}
  }'
```

#### 预期结果

JSON-RPC 响应:
```json
{
  "id": "test-001",
  "result": {
    "tools": [
      {"name": "query_assets", "description": "..."},
      {"name": "query_alerts", "description": "..."}
    ]
  }
}
```

#### 失败处理

1. **检查 Agent 端点是否注册**
   ```bash
   curl http://localhost:8000/openapi.json | jq '.paths["/api/v1/ai/agent/prompt"]'
   ```

2. **检查进程间通信**
   ```bash
   # 查看 Node 进程标准输出
   tail -f /tmp/pi-agent-stdout-*.log
   ```

3. **检查 Service Token**
   - 确认后端 `INTERNAL_SERVICE_TOKEN` 与 Node 进程启动时传入的一致

---

### VP-3: 1 次 LLM 调用成功

#### 检查方法

```bash
TRACE_ID="poc-llm-$(date +%s)"
curl -X POST http://localhost:8000/api/v1/ai/agent/prompt \
  -H "Content-Type: application/json" \
  -H "X-Trace-Id: ${TRACE_ID}" \
  -d '{
    "id": "llm-test-001",
    "method": "agent.prompt",
    "params": {
      "sessionId": "poc-test-session",
      "userMessage": "Hello, this is a POC test. Please respond with a simple greeting.",
      "model": "glm-4-flash"
    }
  }'
```

#### 预期结果

响应包含 `text_delta` 事件流:
```json
{"id":"evt","method":"agent.event","params":{"type":"text_delta","delta":"Hello!","ts":...}}
{"id":"evt","method":"agent.event","params":{"type":"text_delta","delta":" How","ts":...}}
...
{"id":"evt","method":"agent.event","params":{"type":"agent_end","...}}
```

#### 失败处理

1. **检查 LLM 配置**
   ```bash
   # 检查环境变量
   grep -E "PI_|GLM_|ANTHROPIC_|OPENAI_" src/backend/.env

   # 确认至少一个 provider key 已配置
   ```

2. **检查 Node 日志**
   ```bash
   # 查看 pi-agent-runner 输出
   cat /tmp/pi-agent-*.log | grep -i "error\|exception\|fail"
   ```

3. **使用测试模型**
   - POC 阶段可使用 `glm-4-flash` (低成本)
   - 确认模型名称正确: `glm-4-flash`, `claude-sonnet-4-5`, `gpt-4o`

---

### VP-4: Prometheus 看到指标

#### 检查方法

**步骤 1**: 触发一次 LLM 调用 (参见 VP-3)

**步骤 2**: 查询 Prometheus 指标
```bash
curl -s http://localhost:8000/metrics | grep "llm_request_duration"
```

#### 预期结果

```
# HELP llm_request_duration_seconds LLM 请求延迟
# TYPE llm_request_duration_seconds histogram
llm_request_duration_seconds_bucket{model="glm-4-flash",provider="zhipuai",le="0.1"} 1
llm_request_duration_seconds_bucket{model="glm-4-flash",provider="zhipuai",le="0.5"} 1
llm_request_duration_seconds_bucket{model="glm-4-flash",provider="zhipuai",le="1.0"} 1
llm_request_duration_seconds_bucket{model="glm-4-flash",provider="zhipuai",le="+Inf"} 1
llm_request_duration_seconds_count{model="glm-4-flash",provider="zhipuai"} 1
llm_request_duration_seconds_sum{model="glm-4-flash",provider="zhipuai"} 0.823
```

#### 失败处理

1. **确认指标已注册**
   ```bash
   # 检查所有 llm_ 开头的指标
   curl -s http://localhost:8000/metrics | grep "^llm_"

   # 如果没有任何 llm_ 指标，说明指标未注册
   ```

2. **检查 Prometheus 客户端代码**
   - 确认 `prometheus_client` 库已导入
   - 确认 `AgentProcessManager` 初始化时注册了指标

3. **触发调用后再检查**
   - 指标是按需生成的，必须先有 LLM 调用记录

---

### VP-5: Loki 看到结构化日志

#### 检查方法

**步骤 1**: 发送带 trace_id 的测试请求
```bash
TRACE_ID="poc-loki-$(date +%s)-$$"
curl -X POST http://localhost:8000/api/v1/ai/agent/prompt \
  -H "Content-Type: application/json" \
  -H "X-Trace-Id: ${TRACE_ID}" \
  -d '{"id":"1","method":"agent.list_tools","params":{}}'

sleep 3  # 等待日志写入
```

**步骤 2**: 查询 Loki
```bash
curl -G "http://192.168.0.30:3100/loki/api/v1/query_range" \
  --data-urlencode 'query={job="ai-minisoc"}' \
  --data-urlencode "start=$(date -v-10M +%s)000000000" \
  --data-urlencode "end=$(date +%s)000000000" \
  --data-urlencode "limit=10"
```

#### 预期结果

Loki 返回包含以下字段的 JSON 日志:
```json
{
  "stream": {"job": "ai-minisoc"},
  "values": [["1234567890000000000", "{\"ts\":\"...\",\"trace_id\":\"poc-loki-xxx\",\"level\":\"info\",...}"]]
}
```

#### 失败处理

1. **确认 Promtail 运行**
   ```bash
   ssh xiejava@192.168.0.30 'systemctl status promtail'
   ```

2. **检查 Promtail 配置**
   ```bash
   cat /etc/promtail/config.yml | grep -A5 "ai-minisoc"
   ```

3. **测试 Loki 直接写入**
   ```bash
   # 手动推送一条日志测试
   curl -X POST "http://192.168.0.30:3100/loki/api/v1/push" \
     -H "Content-Type: application/json" \
     --data '{"streams":[{"stream":{"job":"ai-minisoc"},"values":[[\"$(date +%s)000000000\",\"{\\\"test\\\":true}\"]]}]}'
   ```

4. **检查日志格式**
   - 后端日志必须是 JSON 格式 (Promtail 的 `json` 解析器)
   - 必须包含 `trace_id` 字段

---

## 自动化验证

使用 `scripts/poc/verify-poc.sh` 自动执行所有验收点检查:

```bash
cd /Users/xiejava/AIproject/AI-miniSOC
bash scripts/poc/verify-poc.sh
```

脚本输出示例:
```
==========================================
   AI-miniSOC Pi Agent POC 验证
==========================================

[INFO] 检查 Node.js 版本...
[PASS] Node.js 版本满足要求 (v20.x.x, 需要 >=20)
...
==========================================
       POC 验证结果报告
==========================================
✅ 全部检查通过
==========================================
```

---

## 前置条件

运行验证前确保:

1. **后端运行**
   ```bash
   cd /Users/xiejava/AIproject/AI-miniSOC/src/backend
   ../../venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

2. **Node.js >= 20**
   ```bash
   node --version  # 必须 >= 20.0.0
   ```

3. **Python 虚拟环境**
   ```bash
   ls -d /Users/xiejava/AIproject/AI-miniSOC/venv
   ```

4. **LLM API Key 配置**
   ```bash
   # 至少配置一个
   grep "PI_PROVIDER_API_KEY\|GLM_API_KEY" src/backend/.env
   ```

---

## 关联文档

- [Pi Agent 集成架构设计](./2026-06-15-pi-ai-integration-design.md)
- [POC 验证脚本说明](../scripts/poc/README.md)
- [现有监控栈说明](../README.md#已部署的监控栈)

---

**版本**: v1.0
**最后更新**: 2026-06-15
**下一步**: 执行 POC 验证，记录结果