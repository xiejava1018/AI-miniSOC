#!/bin/bash
#
# Wazuh API代理服务启动脚本
#

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 检查虚拟环境
if [ -d "venv" ]; then
    echo "使用虚拟环境..."
    source venv/bin/activate
fi

# 检查.env文件
if [ ! -f ".env" ]; then
    echo "警告: .env文件不存在，从.env.example复制..."
    cp .env.example .env
    echo "请编辑.env文件配置正确的凭证"
fi

# 加载环境变量
if [ -f ".env" ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

echo "=========================================="
echo "启动Wazuh API代理服务"
echo "=========================================="
echo "Wazuh URL: ${WAZUH_URL:-https://192.168.0.40:55000}"
echo "监听端口: ${PROXY_PORT:-5000}"
echo "=========================================="
echo ""

# 启动服务
python3 wazuh_proxy.py
