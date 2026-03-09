#!/bin/bash
###############################################################################
# AI-miniSOC 安装脚本
# 作者: xiejava
# 描述: 自动安装AI-miniSOC平台及其依赖
###############################################################################

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查系统要求
check_requirements() {
    log_info "检查系统要求..."

    # 检查操作系统
    if [[ ! "$OSTYPE" == "linux-gnu"* ]]; then
        log_error "不支持的操作系统: $OSTYPE"
        exit 1
    fi

    # 检查内存
    total_mem=$(free -g | awk '/^Mem:/{print $2}')
    if [ "$total_mem" -lt 8 ]; then
        log_warn "建议至少8GB内存，当前: ${total_mem}GB"
    fi

    # 检查磁盘空间
    disk_space=$(df -BG . | awk 'NR==2 {print $4}' | sed 's/G//')
    if [ "$disk_space" -lt 50 ]; then
        log_error "磁盘空间不足，至少需要50GB，当前: ${disk_space}GB"
        exit 1
    fi

    log_info "系统要求检查通过 ✓"
}

# 检查并安装Docker
install_docker() {
    if command -v docker &> /dev/null; then
        log_info "Docker已安装: $(docker --version)"
        return
    fi

    log_info "安装Docker..."
    curl -fsSL https://get.docker.com | sh
    sudo usermod -aG docker $USER

    log_info "Docker安装完成 ✓"
}

# 检查并安装Docker Compose
install_docker_compose() {
    if command -v docker-compose &> /dev/null; then
        log_info "Docker Compose已安装: $(docker-compose --version)"
        return
    fi

    log_info "安装Docker Compose..."
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose

    log_info "Docker Compose安装完成 ✓"
}

# 创建必要的目录
create_directories() {
    log_info "创建目录结构..."

    mkdir -p data/{loki,grafana,wazuh,prometheus,redis,postgres}
    mkdir -p logs
    mkdir -p configs/{wazuh,loki,grafana,alert}
    mkdir -p backups

    log_info "目录创建完成 ✓"
}

# 配置环境变量
setup_env() {
    log_info "配置环境变量..."

    if [ ! -f .env ]; then
        cp .env.example .env
        log_warn "请编辑 .env 文件配置必要的环境变量"
        log_warn "特别是 API keys 和密码配置"
    else
        log_info ".env 文件已存在"
    fi

    log_info "环境变量配置完成 ✓"
}

# 拉取Docker镜像
pull_images() {
    log_info "拉取Docker镜像（这可能需要一些时间）..."

    docker-compose pull

    log_info "Docker镜像拉取完成 ✓"
}

# 启动服务
start_services() {
    log_info "启动AI-miniSOC服务..."

    docker-compose up -d

    log_info "等待服务启动..."
    sleep 10

    log_info "服务启动完成 ✓"
}

# 检查服务状态
check_services() {
    log_info "检查服务状态..."

    services=$(docker-compose ps --services)
    for service in $services; do
        status=$(docker-compose ps -q $service | xargs docker inspect --format='{{.State.Status}}' 2>/dev/null)
        if [ "$status" == "running" ]; then
            log_info "$service: 运行中 ✓"
        else
            log_warn "$service: 未运行 (状态: $status)"
        fi
    done
}

# 显示访问信息
show_access_info() {
    echo ""
    log_info "========================================"
    log_info "AI-miniSOC 安装完成！"
    log_info "========================================"
    echo ""
    log_info "服务访问地址:"
    echo "  • Grafana:      http://localhost:3000"
    echo "  • Wazuh:        https://localhost:55000"
    echo "  • Loki:         http://localhost:3100"
    echo "  • Prometheus:   http://localhost:9090"
    echo ""
    log_info "默认凭据:"
    echo "  • Grafana用户名: admin"
    echo "  • Grafana密码:   admin"
    echo "  • Wazuh用户名:   admin"
    echo "  • Wazuh密码:     请查看 .env 文件"
    echo ""
    log_warn "请修改默认密码！"
    echo ""
    log_info "查看日志:"
    echo "  docker-compose logs -f [service_name]"
    echo ""
    log_info "停止服务:"
    echo "  docker-compose down"
    echo ""
}

# 主安装流程
main() {
    log_info "开始安装AI-miniSOC..."
    echo ""

    check_requirements
    install_docker
    install_docker_compose
    create_directories
    setup_env
    pull_images
    start_services
    check_services
    show_access_info

    log_info "安装脚本执行完成！"
}

# 执行主函数
main "$@"
