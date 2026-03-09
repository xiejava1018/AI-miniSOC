#!/bin/bash
#
# Wazuh API代理服务快速测试脚本
#

PROXY_URL="http://192.168.0.30:5000"

echo "=========================================="
echo "Wazuh API代理服务测试"
echo "=========================================="
echo ""

# 颜色
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# 测试1: 健康检查
echo "测试1: 健康检查"
response=$(curl -s "$PROXY_URL/health")
if echo "$response" | grep -q "healthy"; then
    echo -e "${GREEN}✓ 健康检查通过${NC}"
    echo "$response" | python3 -m json.tool
else
    echo -e "${RED}✗ 健康检查失败${NC}"
    echo "$response"
fi
echo ""

# 测试2: Token信息
echo "测试2: Token信息"
response=$(curl -s "$PROXY_URL/token-info")
echo "$response" | python3 -m json.tool
echo ""

# 测试3: Agents状态汇总
echo "测试3: Agents状态汇总"
response=$(curl -s "$PROXY_URL/agents/summary/status")
if echo "$response" | grep -q "active"; then
    echo -e "${GREEN}✓ API调用成功${NC}"
    echo "$response" | python3 -m json.tool
else
    echo -e "${RED}✗ API调用失败${NC}"
    echo "$response"
fi
echo ""

# 测试4: Agents列表
echo "测试4: Agents列表（前3个）"
response=$(curl -s "$PROXY_URL/agents?limit=3")
if echo "$response" | grep -q "affected_items"; then
    echo -e "${GREEN}✓ Agents列表获取成功${NC}"
    echo "$response" | python3 -m json.tool | head -30
else
    echo -e "${RED}✗ Agents列表获取失败${NC}"
    echo "$response"
fi
echo ""

echo "=========================================="
echo "测试完成"
echo "=========================================="
