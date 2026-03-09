#!/bin/bash
###############################################################################
# AI-miniSOC 系统监控脚本
# 描述: 监控各个服务的健康状态
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 服务列表
SERVICES=(
    "loki"
    "grafana"
    "wazuh-indexer"
    "wazuh-server"
    "wazuh-dashboard"
    "ai-analyzer"
    "alert-engine"
    "log-collector"
    "prometheus"
    "redis"
    "postgres"
)

# 检查容器状态
check_container_status() {
    local service=$1
    local status=$(docker inspect -f '{{.State.Status}}' ${service} 2>/dev/null)

    if [ "$status" == "running" ]; then
        echo -e "${GREEN}✓${NC} $service"
        return 0
    else
        echo -e "${RED}✗${NC} $service (状态: $status)"
        return 1
    fi
}

# 检查HTTP端点
check_http_endpoint() {
    local name=$1
    local url=$2
    local expected_code=${3:-200}

    response=$(curl -s -o /dev/null -w "%{http_code}" "$url" || echo "000")

    if [ "$response" == "$expected_code" ] || [ "${response:0:1}" == "2" ]; then
        echo -e "${GREEN}✓${NC} $name - HTTP $response"
        return 0
    else
        echo -e "${RED}✗${NC} $name - HTTP $response"
        return 1
    fi
}

# 获取容器资源使用情况
get_container_stats() {
    local service=$1
    docker stats --no-stream --format "table {{.Container}}\t{{.CPUPerc}}\t{{.MemUsage}}" $service 2>/dev/null | tail -n +2
}

# 主监控函数
main() {
    echo "========================================="
    echo "AI-miniSOC 系统监控"
    echo "========================================="
    echo ""

    # 检查容器状态
    echo "容器状态:"
    echo "---------"
    running=0
    total=0

    for service in "${SERVICES[@]}"; do
        total=$((total + 1))
        if docker ps --format '{{.Names}}' | grep -q "^${service}$"; then
            if check_container_status "$service"; then
                running=$((running + 1))
            fi
        else
            echo -e "${YELLOW}⊘${NC} $service (未创建)"
        fi
    done

    echo ""
    echo "运行服务: $running / $total"
    echo ""

    # 检查HTTP端点
    echo "服务端点:"
    echo "---------"
    check_http_endpoint "Loki" "http://localhost:3100/ready"
    check_http_endpoint "Grafana" "http://localhost:3000/api/health"
    check_http_endpoint "Prometheus" "http://localhost:9090/-/healthy"
    echo ""

    # 显示资源使用
    echo "资源使用:"
    echo "---------"
    for service in "${SERVICES[@]}"; do
        if docker ps --format '{{.Names}}' | grep -q "^${service}$"; then
            stats=$(get_container_stats "$service")
            if [ -n "$stats" ]; then
                echo "$stats"
            fi
        fi
    done
    echo ""

    # 磁盘使用
    echo "磁盘使用:"
    echo "---------"
    df -h | grep -E "(Filesystem|/dev/sd|/dev/nvme)"
    echo ""

    # Docker卷使用
    echo "Docker卷使用:"
    echo "---------"
    docker system df -v 2>/dev/null | head -20
}

# 执行主函数
main "$@"
