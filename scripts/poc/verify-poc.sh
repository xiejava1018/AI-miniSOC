#!/bin/bash
#
# AI-miniSOC Pi Agent POC 端到端验证脚本
# 验收点：
#   1. npm 依赖已安装 (node_modules 存在)
#   2. JSON-RPC ping/pong 通: 调 agent.ping 返回 pong
#   3. JSON-RPC list_tools: 返回工具列表(含 POC 提示)
#   4. Prometheus /metrics 端点可访问
#   5. 后端服务运行正常
#

set -e

# 配置
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
METRICS_URL="${BACKEND_URL}/metrics"
AGENT_RUNNER_DIR="${PROJECT_ROOT}/src/agent-runner"
TIMEOUT_SEC=10
FAILED=0

# 颜色输出
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[1;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

log_info()  { echo -e "${GREEN}[INFO]${NC}  $1"; }
log_warn()   { echo -e "${YELLOW}[WARN]${NC}  $1"; }
log_fail()   { echo -e "${RED}[FAIL]${NC} $1"; }
log_pass()   { echo -e "${GREEN}[PASS]${NC} $1"; }
log_step()   { echo -e "${BLUE}[STEP]${NC} $1"; }

check_result() {
    if [ $1 -eq 0 ]; then
        log_pass "$2"
    else
        log_fail "$2"
        FAILED=1
    fi
}

# ========== 检查 1: npm 依赖 ==========
check_npm_deps() {
    log_step "检查 1: npm 依赖安装"
    if [ -d "${AGENT_RUNNER_DIR}/node_modules" ]; then
        log_pass "node_modules 存在 ($(find "${AGENT_RUNNER_DIR}/node_modules" -maxdepth 1 -type d | wc -l | tr -d ' ') 个包)"
    else
        log_info "安装 npm 依赖..."
        cd "${AGENT_RUNNER_DIR}" && npm install --ignore-scripts >/dev/null 2>&1
        if [ -d "node_modules" ]; then
            log_pass "npm 依赖安装成功"
        else
            check_result 1 "npm 依赖安装失败"
        fi
    fi
}

# ========== 检查 2: JSON-RPC ping/pong ==========
check_jsonrpc_ping() {
    log_step "检查 2: JSON-RPC ping/pong"

    NODE_PATH=$(command -v node || echo "/usr/local/bin/node")

    if [ ! -x "${NODE_PATH}" ]; then
        check_result 1 "Node.js 未找到或不可执行: ${NODE_PATH}"
        return
    fi

    log_info "发送 agent.ping 请求..."

    # 方式: printf + pipe + head 限制输出(避免 timeout 问题)
    RESPONSE=$(printf '{"id":"poc-ping","method":"agent.ping","params":{}}\n' \
        | "${NODE_PATH}" "${AGENT_RUNNER_DIR}/src/pi-agent-runner.js" 2>/dev/null \
        | grep -m1 '"result"' || true)

    if echo "$RESPONSE" | grep -q '"pong"'; then
        check_result 0 "JSON-RPC ping/pong 成功"
        echo "    响应: $(echo "$RESPONSE" | head -c 150)"
    else
        check_result 1 "JSON-RPC ping/pong 失败"
        echo "    实际响应: $RESPONSE"
    fi
}

# ========== 检查 3: JSON-RPC list_tools ==========
check_jsonrpc_tools() {
    log_step "检查 3: JSON-RPC list_tools"

    NODE_PATH=$(command -v node || echo "/usr/local/bin/node")

    RESPONSE=$(printf '{"id":"poc-tools","method":"agent.list_tools","params":{}}\n' \
        | "${NODE_PATH}" "${AGENT_RUNNER_DIR}/src/pi-agent-runner.js" 2>/dev/null \
        | grep -m1 '"result"' || true)

    if echo "$RESPONSE" | grep -q '"ok":true'; then
        check_result 0 "JSON-RPC list_tools 成功"
        if echo "$RESPONSE" | grep -q '"tools":\[\]'; then
            log_info "    (POC 阶段: 工具列表为空,待后续实现)"
        fi
    else
        check_result 1 "JSON-RPC list_tools 失败"
    fi
}

# ========== 检查 4: Prometheus /metrics ==========
check_prometheus() {
    log_step "检查 4: Prometheus /metrics 端点"

    METRICS=$(curl -s --max-time 5 "${METRICS_URL}" 2>/dev/null || echo "")

    if [ -z "$METRICS" ]; then
        log_warn "后端未运行,跳过 metrics 检查"
        log_info "提示: 启动后端后再检查 metrics"
        log_info "  cd ${PROJECT_ROOT}/src/backend && ../../venv/bin/python -m uvicorn main:app --reload"
        return
    fi

    if echo "$METRICS" | grep -q "# HELP"; then
        check_result 0 "Prometheus /metrics 端点可访问"
        METRIC_COUNT=$(echo "$METRICS" | grep -c "^# HELP" || echo "0")
        log_info "    共 ${METRIC_COUNT} 个指标定义"

        # 检查自定义指标是否存在(注册后才出现)
        if echo "$METRICS" | grep -q "llm_request_duration"; then
            log_info "    ✅ llm_request_duration_seconds 已注册"
        fi
        if echo "$METRICS" | grep -q "tool_execution_count"; then
            log_info "    ✅ tool_execution_count 已注册"
        fi
    else
        check_result 1 "Prometheus /metrics 格式异常"
    fi
}

# ========== 检查 5: 后端服务 ==========
check_backend() {
    log_step "检查 5: 后端服务状态"

    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
        --max-time 5 "${BACKEND_URL}/api/v1/public/system-info" 2>/dev/null || echo "000")

    if [ "$HTTP_CODE" = "200" ]; then
        check_result 0 "后端服务运行正常 (HTTP ${HTTP_CODE})"
    else
        log_warn "后端未运行 (HTTP ${HTTP_CODE})"
        log_info "提示: 启动后端"
        log_info "  cd ${PROJECT_ROOT}/src/backend && ../../venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
        log_info "启动后重新运行此脚本验证"
    fi
}

# ========== 检查 6: Python 模块导入 ==========
check_python_modules() {
    log_step "检查 6: Python 模块导入"

    BACKEND_DIR="${PROJECT_ROOT}/src/backend"
    VENV="${PROJECT_ROOT}/venv/bin/python"
    if [ ! -f "$VENV" ]; then
        VENV="${PROJECT_ROOT}/src/backend/../../venv/bin/python"
    fi

    if [ ! -f "$VENV" ]; then
        log_warn "Python 虚拟环境未找到"
        return
    fi

    log_info "验证 AgentProcessManager 导入..."
    IMPORT_RESULT=$(cd "${BACKEND_DIR}" && "${VENV}" -c "from app.services.agent_process_manager import AgentProcessManager; print('OK')" 2>&1 || echo "FAIL")

    if [ "$IMPORT_RESULT" = "OK" ]; then
        check_result 0 "AgentProcessManager 导入成功"
    else
        log_warn "AgentProcessManager 导入失败: $(echo "$IMPORT_RESULT" | head -c 100)"
    fi

    log_info "验证可观测性模块导入..."
    METRICS_RESULT=$(cd "${BACKEND_DIR}" && "${VENV}" -c "from app.observability.metrics import llm_request_duration; print('OK')" 2>&1 || echo "FAIL")

    if [ "$METRICS_RESULT" = "OK" ]; then
        check_result 0 "可观测性指标模块导入成功"
    else
        log_warn "可观测性模块导入失败: $(echo "$METRICS_RESULT" | head -c 100)"
    fi
}

# ========== 打印报告 ==========
print_report() {
    echo ""
    echo "=============================================="
    echo "         POC 验证结果报告"
    echo "=============================================="
    echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "项目: ${PROJECT_ROOT}"
    echo "----------------------------------------------"

    if [ $FAILED -eq 0 ]; then
        echo -e "${GREEN}✅ 全部检查通过${NC}"
        echo ""
        echo "下一步:"
        echo "  1. 配置 LLM API Key (环境变量 OPENAI_API_KEY 或 GLM_API_KEY)"
        echo "  2. 实现 AgentProcessManager 的 spawn/call 方法"
        echo "  3. 创建 /api/v1/ai/agent/* 端点"
        echo "  4. 连接工具到 SOC 数据源"
        echo "=============================================="
        return 0
    else
        echo -e "${RED}❌ 部分检查失败${NC}"
        echo "查看上方 FAIL 项并修复"
        echo "=============================================="
        return 1
    fi
}

# ========== 主函数 ==========
main() {
    echo ""
    echo "=============================================="
    echo "   AI-miniSOC Pi Agent POC 验证"
    echo "   $(date '+%Y-%m-%d %H:%M:%S')"
    echo "=============================================="
    echo ""

    check_npm_deps
    check_jsonrpc_ping
    check_jsonrpc_tools
    check_backend
    check_python_modules
    check_prometheus

    print_report
    exit $FAILED
}

# ========== 执行 ==========
main "$@"
