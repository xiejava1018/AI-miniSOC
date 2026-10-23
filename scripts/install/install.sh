#!/bin/bash
###############################################################################
# AI-miniSOC 采集器安装脚本
# 作者: xiejava
# 描述: 自动安装 AI-miniSOC 采集器（TP-Link 路由器 / Wazuh / 扫描器）
#
# 2026-10（issue #12）修复：
#   1. **compose 文件路径**：原脚本在仓库根目录跑 `docker-compose`，
#      但 compose 文件在 src/collectors/docker-compose.yaml，直接跑必然
#      "no such file: docker-compose.yaml"。现统一定位 COMPOSE_FILE 并
#      所有 docker compose 调用都带 -f。
#   2. **docker compose vs docker-compose**：新版 Docker 只有插件式
#      `docker compose`，没有独立的 `docker-compose` 可执行文件。
#      自动探测，优先用插件式。
#   3. **默认账号密码**：安装完成后明确打印 AI-miniSOC 后台登录凭据
#      （admin / 出厂密码），此前脚本只打印 Grafana/Wazuh 凭据，
#      部署者根本不知道 AI-miniSOC 自己怎么登录。
#   4. **健康检查**：sleep 10 改为轮询 /health（后端冷启动 8s+，
#      CLAUDE.md §4.10），避免误报失败。
###############################################################################

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ---------- 路径解析（脚本可能在任意 cwd 被调用） ----------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
COLLECTORS_DIR="${REPO_ROOT}/src/collectors"
COMPOSE_FILE="${COLLECTORS_DIR}/docker-compose.yaml"
ENV_FILE="${REPO_ROOT}/.env"

# docker compose 调用前缀（探测插件式 vs 独立可执行文件）
COMPOSE_CMD=()

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# ---------- 检查系统要求 ----------
check_requirements() {
    log_info "检查系统要求..."

    if [[ ! "$OSTYPE" == "linux-gnu"* ]]; then
        log_error "不支持的操作系统: $OSTYPE（采集器需要 Linux + Docker）"
        exit 1
    fi

    local total_mem
    total_mem=$(free -g | awk '/^Mem:/{print $2}')
    if [ "$total_mem" -lt 4 ]; then
        log_warn "建议至少 4GB 内存，当前: ${total_mem}GB"
    fi

    local disk_space
    disk_space=$(df -BG "${REPO_ROOT}" | awk 'NR==2 {print $4}' | sed 's/G//')
    if [ "${disk_space}" -lt 20 ]; then
        log_error "磁盘空间不足，至少需要 20GB，当前: ${disk_space}GB"
        exit 1
    fi

    log_info "系统要求检查通过 ✓"
}

# ---------- 检查并安装 Docker ----------
install_docker() {
    if command -v docker &> /dev/null; then
        log_info "Docker 已安装: $(docker --version)"
    else
        log_info "安装 Docker..."
        curl -fsSL https://get.docker.com | sh
        sudo usermod -aG docker "$USER"
        log_warn "已把 ${USER} 加入 docker 组，需重新登录后生效"
    fi
}

# ---------- 探测 docker compose ----------
setup_compose_cmd() {
    log_info "检查 Docker Compose..."

    if docker compose version &> /dev/null; then
        COMPOSE_CMD=(docker compose)
        log_info "使用插件式: $(docker compose version --short 2>/dev/null || echo 'docker compose')"
        return
    fi

    if command -v docker-compose &> /dev/null; then
        COMPOSE_CMD=(docker-compose)
        log_info "使用独立命令: $(docker-compose --version)"
        return
    fi

    log_info "安装 Docker Compose 插件..."
    sudo apt-get update -qq || true
    sudo apt-get install -y docker-compose-plugin || \
        sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose

    if docker compose version &> /dev/null; then
        COMPOSE_CMD=(docker compose)
    elif command -v docker-compose &> /dev/null; then
        COMPOSE_CMD=(docker-compose)
    else
        log_error "Docker Compose 安装失败"
        exit 1
    fi
}

# ---------- 校验 compose 文件存在 ----------
check_compose_file() {
    if [ ! -f "${COMPOSE_FILE}" ]; then
        log_error "找不到 compose 文件: ${COMPOSE_FILE}"
        log_error "请确认克隆的是完整仓库（该文件在 src/collectors/ 下）"
        exit 1
    fi
    log_info "compose 文件: ${COMPOSE_FILE}"
}

# ---------- 配置环境变量 ----------
setup_env() {
    log_info "配置环境变量..."

    if [ ! -f "${ENV_FILE}" ]; then
        local example="${REPO_ROOT}/.env.example"
        if [ -f "${example}" ]; then
            cp "${example}" "${ENV_FILE}"
            log_warn "已从 .env.example 生成 .env"
        else
            log_warn "未找到 .env.example，跳过 .env 生成"
        fi
    else
        log_info ".env 已存在"
    fi

    if [ -f "${ENV_FILE}" ]; then
        # shellcheck disable=SC1090
        set -a; source "${ENV_FILE}"; set +a
        log_info "已加载 .env"
    fi

    if [ -z "${MINISOC_API_KEY:-}" ]; then
        log_warn "MINISOC_API_KEY 未配置——采集器将无法上报数据"
        log_warn "请在 .env 里填入后端「扫描器/MCP Key」页面签发的 Key"
    fi
}

# ---------- 拉取镜像 ----------
pull_images() {
    log_info "拉取/构建镜像（首次会现场 build，可能需要几分钟）..."
    "${COMPOSE_CMD[@]}" -f "${COMPOSE_FILE}" pull || \
        log_warn "部分镜像拉取失败，将改为本地构建"
    "${COMPOSE_CMD[@]}" -f "${COMPOSE_FILE}" build
    log_info "镜像准备完成 ✓"
}

# ---------- 启动服务 ----------
start_services() {
    log_info "启动采集器服务..."
    "${COMPOSE_CMD[@]}" -f "${COMPOSE_FILE}" up -d
    log_info "服务已启动，等待健康检查..."
}

# ---------- 轮询健康检查（不用固定 sleep） ----------
wait_healthy() {
    local timeout="${1:-120}"
    local waited=0
    while [ "${waited}" -lt "${timeout}" ]; do
        local unhealthy
        unhealthy=$("${COMPOSE_CMD[@]}" -f "${COMPOSE_FILE}" ps \
            --format '{{.Service}} {{.Health}}' 2>/dev/null | grep -c 'unhealthy\|starting' || true)
        if [ "${unhealthy}" -eq 0 ]; then
            log_info "全部服务健康 ✓"
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
    done
    log_warn "等待 ${timeout}s 后仍有服务未就绪，继续（可用 docker compose ps 查看）"
    return 0
}

# ---------- 检查服务状态 ----------
check_services() {
    log_info "服务状态："
    "${COMPOSE_CMD[@]}" -f "${COMPOSE_FILE}" ps || true
}

# ---------- 显示访问信息 ----------
show_access_info() {
    local admin_password="${DEFAULT_ADMIN_PASSWORD:-Admin@123456}"

    echo ""
    log_info "========================================"
    log_info "AI-miniSOC 采集器安装完成！"
    log_info "========================================"
    echo ""
    log_info "【AI-miniSOC 后台登录】"
    echo "  • 地址:     http://<后端地址>:8000  （前端见 nginx 配置）"
    echo "  • 用户名:   admin"
    echo "  • 密码:     ${admin_password}"
    echo ""
    log_warn "以上为出厂默认密码，首次登录后请立即在「系统管理 → 用户管理」修改！"
    echo ""
    log_info "【可选依赖服务】（compose 文件里默认不含，按需单独部署）"
    echo "  • Grafana:    http://localhost:3000   admin/admin"
    echo "  • Wazuh:      https://localhost:55000 admin / 见 .env"
    echo "  • Loki:       http://localhost:3100"
    echo "  • Prometheus: http://localhost:9090"
    echo ""
    log_info "常用命令（在 ${COLLECTORS_DIR} 下执行，或加 -f ${COMPOSE_FILE}）:"
    echo "  查看日志:   ${COMPOSE_CMD[*]} -f ${COMPOSE_FILE} logs -f [service]"
    echo "  重启:       ${COMPOSE_CMD[*]} -f ${COMPOSE_FILE} restart"
    echo "  停止:       ${COMPOSE_CMD[*]} -f ${COMPOSE_FILE} down"
    echo ""
    echo "提示：采集器需要后端已启动并已配置 DB，数据库初始化见 README「快速开始」。"
    echo ""
}

# ---------- 主流程 ----------
main() {
    log_info "开始安装 AI-miniSOC 采集器..."
    echo "  仓库根目录: ${REPO_ROOT}"
    echo ""

    check_requirements
    install_docker
    setup_compose_cmd
    check_compose_file
    setup_env
    pull_images
    start_services
    wait_healthy "${WAIT_TIMEOUT:-120}"
    check_services
    show_access_info

    log_info "安装脚本执行完成！"
}

main "$@"