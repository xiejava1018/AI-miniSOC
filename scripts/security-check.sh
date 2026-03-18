#!/bin/bash
###############################################################################
# AI-miniSOC 安全检查脚本
# 在提交前检查是否有敏感信息
###############################################################################

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查计数
ERRORS=0
WARNINGS=0

echo "🔍 开始安全检查..."
echo "========================================="

# 1. 检查硬编码密码
echo ""
echo "📋 检查硬编码密码..."
if git grep -n "password\s*=\s*['\"][^'\"]*['\"]" -- '*.py' '*.sh' '*.yml' '*.yaml' '*.json' 2>/dev/null | \
   grep -v "os.getenv" | \
   grep -v "example" | \
   grep -v "your_password_here" | \
   grep -v "SECURITY.md"; then
    echo -e "${RED}❌ 发现硬编码密码！${NC}"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}✅ 未发现硬编码密码${NC}"
fi

# 2. 检查API密钥
echo ""
echo "📋 检查API密钥..."
if git grep -i -n "api_key\s*=\s*['\"][^'\"]{20,}['\"]" -- '*.py' '*.sh' '*.js' '*.ts' 2>/dev/null | \
   grep -v "os.getenv" | \
   grep -v "example" | \
   grep -v "your_api_key_here"; then
    echo -e "${RED}❌ 发现硬编码API密钥！${NC}"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}✅ 未发现硬编码API密钥${NC}"
fi

# 3. 检查Token
echo ""
echo "📋 检查Token..."
if git grep -i -n "token\s*=\s*['\"][^'\"]{20,}['\"]" -- '*.py' '*.sh' 2>/dev/null | \
   grep -v "os.getenv" | \
   grep -v "example" | \
   grep -v "your_token_here" | \
   grep -v "jwt" | \
   grep -v "csrf"; then
    echo -e "${RED}❌ 发现硬编码Token！${NC}"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}✅ 未发现硬编码Token${NC}"
fi

# 4. 检查.env文件
echo ""
echo "📋 检查.env文件..."
if git ls-files | grep -E "\.env$"; then
    echo -e "${RED}❌ .env文件被Git跟踪！${NC}"
    git ls-files | grep -E "\.env$"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}✅ .env文件未被跟踪${NC}"
fi

# 5. 检查备份文件
echo ""
echo "📋 检查备份文件..."
if git ls-files | grep -E "\.(backup|bak|old|tmp)$"; then
    echo -e "${YELLOW}⚠️  发现备份文件被跟踪：${NC}"
    git ls-files | grep -E "\.(backup|bak|old|tmp)$"
    WARNINGS=$((WARNINGS + 1))
else
    echo -e "${GREEN}✅ 未发现备份文件${NC}"
fi

# 6. 检查虚拟环境
echo ""
echo "📋 检查虚拟环境..."
if git ls-files | grep -E "venv/|env/|.venv/"; then
    echo -e "${RED}❌ 虚拟环境被Git跟踪！${NC}"
    git ls-files | grep -E "venv/|env/|.venv/"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}✅ 虚拟环境未被跟踪${NC}"
fi

# 7. 检查证书文件
echo ""
echo "📋 检查证书文件..."
if git ls-files | grep -E "\.(pem|crt|key|p12|pfx)$"; then
    echo -e "${RED}❌ 发现证书文件被跟踪！${NC}"
    git ls-files | grep -E "\.(pem|crt|key|p12|pfx)$"
    ERRORS=$((ERRORS + 1))
else
    echo -e "${GREEN}✅ 未发现证书文件${NC}"
fi

# 总结
echo ""
echo "========================================="
if [ $ERRORS -gt 0 ]; then
    echo -e "${RED}❌ 发现 $ERRORS 个错误，$WARNINGS 个警告${NC}"
    echo -e "${RED}请修复错误后再提交！${NC}"
    exit 1
elif [ $WARNINGS -gt 0 ]; then
    echo -e "${YELLOW}⚠️  发现 $WARNINGS 个警告${NC}"
    echo -e "${YELLOW}请检查警告内容${NC}"
    exit 0
else
    echo -e "${GREEN}✅ 安全检查通过！${NC}"
    exit 0
fi
