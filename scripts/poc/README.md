# POC 验证脚本

本目录包含 AI-miniSOC Pi Agent 集成的端到端验证脚本。

## 文件清单

| 文件 | 说明 |
|------|------|
| `verify-poc.sh` | POC 端到端验证脚本 |
| `README.md` | 本文档 |

## POC 验收清单

| # | 验收点 | 检查方法 | 预期结果 |
|---|--------|----------|----------|
| 1 | Node 进程被 spawn | `pgrep -f pi-agent-runner` | 至少 1 个进程运行 |
| 2 | JSON-RPC ping/pong 通 | `POST /api/v1/ai/agent/prompt` with `agent.list_tools` | 返回工具列表 |
| 3 | 1 次 LLM 调用成功 | `POST /api/v1/ai/agent/prompt` | 返回 `text_delta` 事件流 |
| 4 | Prometheus 看到指标 | `curl /metrics` | 包含 `llm_request_duration_seconds` |
| 5 | Loki 看到结构化日志 | Loki 查询 `{job="ai-minisoc"}` | 包含 `trace_id` 字段的 JSON 日志 |

## 启动顺序

### 1. 启动后端

```bash
cd /Users/xiejava/AIproject/AI-miniSOC/src/backend
../venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. 启动 pi-agent-runner (Node 进程池)

```bash
cd /opt/ai-minisoc/agent-runner
node pi-agent-runner.js --stdio --config /etc/pi/config.json
```

> **注意**: Pi Agent 进程由后端 `AgentProcessManager` 按需 spawn，无需手动启动。
> 手动启动仅用于独立调试。

### 3. 运行验证脚本

```bash
cd /Users/xiejava/AIproject/AI-miniSOC
bash scripts/poc/verify-poc.sh
```

## 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `BACKEND_URL` | `http://localhost:8000` | 后端地址 |
| `LOKI_URL` | `http://192.168.0.30:3100` | Loki 地址 |

## 预期输出示例

```
==========================================
   AI-miniSOC Pi Agent POC 验证
==========================================

[INFO] 检查 Node.js 版本...
[PASS] Node.js 版本满足要求 (v20.x.x, 需要 >=20)
[INFO] 检查 Python 虚拟环境...
[PASS] Python 虚拟环境存在 (/Users/xiejava/AIproject/AI-miniSOC/venv)
[INFO] 检查后端服务 (http://localhost:8000)...
[PASS] 后端服务运行正常 (HTTP 200)
[INFO] 检查 pi-agent-runner 进程...
[PASS] pi-agent-runner 进程运行中 (PID: 12345)
[INFO] 测试 JSON-RPC ping/pong (agent.list_tools)...
[PASS] JSON-RPC ping/pong 成功
[INFO] 测试 LLM 调用 (text_delta 事件流)...
[PASS] LLM 调用成功，返回 text_delta 事件
[INFO] 检查 Prometheus 指标 (llm_request_duration_seconds)...
[PASS] Prometheus 指标 llm_request_duration_seconds 存在
[INFO] 检查 Loki 结构化日志 (trace_id 字段)...
[PASS] Loki 包含 trace_id 结构化日志

==========================================
       POC 验证结果报告
==========================================
时间: 2026-06-15 12:00:00
后端: http://localhost:8000
----------------------------------------
✅ 全部检查通过
==========================================
```

## 失败排查指引

### 1. Node.js 版本检查失败

**问题**: `Node.js 未安装` 或 `版本过低`

**解决**:
```bash
# macOS 使用 Homebrew
brew install node@20

# 验证
node --version  # 应显示 v20.x.x
```

### 2. 后端服务无响应

**问题**: `后端服务未响应 (HTTP 000)`

**排查**:
```bash
# 检查后端进程
ps aux | grep uvicorn

# 检查端口占用
lsof -i :8000

# 查看后端日志
cd src/backend && tail -f logs/*.log
```

### 3. pi-agent-runner 进程未运行

**问题**: `pi-agent-runner 进程未运行`

**排查**:
```bash
# 检查后端是否正确 spawn 了进程
ps aux | grep -E "pi-agent|node"

# 检查 Node 进程是否有错误
tail -f /tmp/pi-agent-*.log

# 检查配置文件
cat /etc/pi/config.json
```

### 4. JSON-RPC 请求失败

**问题**: `JSON-RPC 请求无响应` 或 `ping/pong 失败`

**排查**:
```bash
# 直接测试 agent 端点
curl -X POST http://localhost:8000/api/v1/ai/agent/prompt \
  -H "Content-Type: application/json" \
  -H "X-Trace-Id: test-001" \
  -d '{"id":"1","method":"agent.list_tools","params":{}}'

# 检查后端路由是否注册
curl http://localhost:8000/openapi.json | jq '.paths[] | keys'
```

### 5. LLM 调用失败

**问题**: `LLM 调用失败` 或 `配置缺失`

**排查**:
```bash
# 检查环境变量
grep -E "PI_|GLM_|ANTHROPIC_" src/backend/.env

# 确认 API Key 已配置
# 必需: PI_PROVIDER_API_KEY 或 GLM_API_KEY
```

### 6. Prometheus 指标缺失

**问题**: `未找到 llm_request_duration_seconds 指标`

**排查**:
```bash
# 检查 /metrics 端点
curl http://localhost:8000/metrics

# 检查指标是否注册 (搜索其他 llm_ 开头的指标)
curl -s http://localhost:8000/metrics | grep "^llm_"

# 触发一次 LLM 调用后再检查
```

### 7. Loki 日志未找到

**问题**: `Loki 可访问但未找到 trace_id`

**排查**:
```bash
# 检查 Promtail 状态
ssh xiejava@192.168.0.30 'systemctl status promtail'

# 检查 Loki 是否有数据
curl "http://192.168.0.30:3100/loki/api/v1/series" --data-raw '{}'

# 直接查询最近的日志
curl -G "http://192.168.0.30:3100/loki/api/v1/query" \
  --data-urlencode 'query={job="ai-minisoc"}' \
  --data-urlencode 'limit=5'
```

## 单独运行测试

脚本支持单独运行某个测试函数:

```bash
# 仅测试后端
source <(grep -E "^test_backend_only" scripts/poc/verify-poc.sh | sed 's/()//')

# 或直接调用
bash -c 'source scripts/poc/verify-poc.sh && test_backend_only'
```

## 相关文档

- 设计文档: `docs/plans/2026-06-15-pi-ai-integration-design.md`
- POC 验证清单: `docs/plans/2026-06-15-poc-verification-checklist.md`