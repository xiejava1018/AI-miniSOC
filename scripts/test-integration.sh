#!/bin/bash
# 前后端集成测试脚本

echo "========================================="
echo "  AI-miniSOC 前后端集成测试"
echo "========================================="
echo ""

# 颜色定义
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 测试后端健康检查
echo -n "1. 测试后端健康检查... "
HEALTH=$(curl -s http://localhost:8000/health)
if echo "$HEALTH" | grep -q "healthy"; then
    echo -e "${GREEN}✓ 通过${NC}"
    echo "   后端状态: 正常"
else
    echo -e "${RED}✗ 失败${NC}"
    echo "   后端未响应"
    exit 1
fi

# 测试资产API
echo -n "2. 测试资产API... "
ASSETS=$(curl -s "http://localhost:8000/api/v1/assets/?limit=1")
if echo "$ASSETS" | grep -q "items"; then
    echo -e "${GREEN}✓ 通过${NC}"
    TOTAL=$(echo "$ASSETS" | python3 -c "import sys, json; print(json.load(sys.stdin)['total'])" 2>/dev/null || echo "未知")
    echo "   资产总数: $TOTAL"
else
    echo -e "${RED}✗ 失败${NC}"
fi

# 测试Wazuh同步
echo -n "3. 测试Wazuh资产同步... "
SYNC=$(curl -s -X POST http://localhost:8000/api/v1/assets/sync/from-wazuh)
if echo "$SYNC" | grep -q "completed"; then
    echo -e "${GREEN}✓ 通过${NC}"
else
    echo -e "${YELLOW}⚠ 警告${NC}"
fi

# 测试AI分析
echo -n "4. 测试AI分析... "
AI_RESPONSE=$(curl -s -X POST http://localhost:8000/api/v1/ai/analyze-alert \
  -H "Content-Type: application/json" \
  -d '{
    "alert_id": "integration_test_001",
    "rule_level": 5,
    "rule_description": "测试告警"
  }')

if echo "$AI_RESPONSE" | grep -q "explanation"; then
    echo -e "${GREEN}✓ 通过${NC}"
    echo "   AI分析已生成"
else
    echo -e "${RED}✗ 失败${NC}"
    echo "   错误: $AI_RESPONSE" | head -50
fi

# 测试告警API
echo -n "5. 测试告警统计API... "
STATS=$(curl -s "http://localhost:8000/api/v1/alerts/statistics?hours=24")
if echo "$STATS" | grep -q "period"; then
    echo -e "${GREEN}✓ 通过${NC}"
else
    echo -e "${YELLOW}⚠ 警告${NC}"
fi

echo ""
echo "========================================="
echo "  测试完成！"
echo "========================================="
echo ""
echo "📱 访问地址:"
echo "   前端: http://localhost:5173"
echo "   后端API文档: http://localhost:8000/docs"
echo ""
echo "🎯 主要功能:"
echo "   - 概览仪表板: /dashboard"
echo "   - 资产管理: /assets"
echo "   - 事件管理: /incidents"
echo "   - 告警管理: /alerts"
echo ""
