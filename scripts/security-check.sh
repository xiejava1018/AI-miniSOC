#!/bin/bash
# 🔒 敏感信息安全检查脚本
# 用于检查代码和文档中是否包含敏感信息

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║          🔒 AI-miniSOC 敏感信息安全检查                      ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查计数
issues_found=0

echo "🔍 开始安全检查..."
echo ""

# 检查1: 数据库密码
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 检查数据库硬编码密码"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if grep -r "PostgreSQL@" docs/ scripts/ 2>/dev/null | grep -v ".git" > /dev/null; then
    echo -e "${RED}❌ 发现硬编码的数据库密码！${NC}"
    grep -rn "PostgreSQL@" docs/ scripts/ 2>/dev/null | grep -v ".git"
    ((issues_found++))
else
    echo -e "${GREEN}✅ 未发现硬编码的数据库密码${NC}"
fi
echo ""

# 检查2: Wazuh密码
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 检查Wazuh API密码"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if grep -r "OgdHes6S57Y" docs/ scripts/ 2>/dev/null | grep -v ".git" > /dev/null; then
    echo -e "${RED}❌ 发现Wazuh API密码！${NC}"
    grep -rn "OgdHes6S57Y" docs/ scripts/ 2>/dev/null | grep -v ".git"
    ((issues_found++))
else
    echo -e "${GREEN}✅ 未发现Wazuh API密码${NC}"
fi
echo ""

# 检查3: API密钥
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 检查智谱AI API密钥"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if grep -r "0735840d01d94776a902d6b787b20908" docs/ scripts/ 2>/dev/null | grep -v ".git" > /dev/null; then
    echo -e "${RED}❌ 发现智谱AI API密钥！${NC}"
    grep -rn "0735840d01d94776a902d6b787b20908" docs/ scripts/ 2>/dev/null | grep -v ".git"
    ((issues_found++))
else
    echo -e "${GREEN}✅ 未发现智谱AI API密钥${NC}"
fi
echo ""

# 检查4: JWT密钥
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 检查JWT密钥"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if grep -r "a5b8e5eb20859e13092cabe0c4adda6c755c9d7bc0395306cc6784d1084e7ae2" docs/ scripts/ 2>/dev/null | grep -v ".git" > /dev/null; then
    echo -e "${RED}❌ 发现JWT密钥！${NC}"
    grep -rn "a5b8e5eb20859e13092cabe0c4adda6c755c9d7bc0395306cc6784d1084e7ae2" docs/ scripts/ 2>/dev/null | grep -v ".git"
    ((issues_found++))
else
    echo -e "${GREEN}✅ 未发现JWT密钥${NC}"
fi
echo ""

# 检查5: 敏感文件模式
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 检查PGPASSWORD环境变量使用"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if grep -r "PGPASSWORD='.+'" docs/ scripts/ 2>/dev/null | grep -v ".git" | grep -v "见环境变量" > /dev/null; then
    echo -e "${YELLOW}⚠️  发现可能的硬编码密码：${NC}"
    grep -rn "PGPASSWORD='.+'" docs/ scripts/ 2>/dev/null | grep -v ".git" | grep -v "见环境变量" | head -10
    ((issues_found++))
else
    echo -e "${GREEN}✅ 未发现硬编码的PGPASSWORD${NC}"
fi
echo ""

# 检查6: .env文件是否被跟踪
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 检查.env文件是否被Git跟踪"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if git ls-files 2>/dev/null | grep -q "^\.env$"; then
    echo -e "${RED}❌ .env文件被Git跟踪！这是严重的安全问题！${NC}"
    echo "   请立即运行: git rm --cached .env"
    ((issues_found++))
else
    echo -e "${GREEN}✅ .env文件未被Git跟踪${NC}"
fi
echo ""

# 检查7: 备份目录是否被跟踪
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 检查dbbackup目录是否被Git跟踪"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if git ls-files 2>/dev/null | grep "^dbbackup/" > /dev/null; then
    echo -e "${YELLOW}⚠️  dbbackup目录中有文件被Git跟踪${NC}"
    git ls-files 2>/dev/null | grep "^dbbackup/"
    ((issues_found++))
else
    echo -e "${GREEN}✅ dbbackup目录未被Git跟踪${NC}"
fi
echo ""

# 总结
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 检查总结"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $issues_found -eq 0 ]; then
    echo -e "${GREEN}✅ 未发现敏感信息泄露问题${NC}"
    echo ""
    echo "🎉 安全检查通过！"
    exit 0
else
    echo -e "${RED}❌ 发现 $issues_found 个安全问题${NC}"
    echo ""
    echo "⚠️  请立即修复上述问题后再提交代码！"
    echo ""
    echo "📖 参考文档: docs/development/security-checklist.md"
    exit 1
fi
