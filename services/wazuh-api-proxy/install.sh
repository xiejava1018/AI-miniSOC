#!/bin/bash
#
# Wazuh API代理服务安装脚本
#

set -e

echo "=========================================="
echo "Wazuh API代理服务安装脚本"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否为root用户
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}错误: 请使用sudo运行此脚本${NC}"
    exit 1
fi

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SERVICE_USER="xiejava"
SERVICE_DIR="$SCRIPT_DIR"
VENV_DIR="$SERVICE_DIR/venv"
SERVICE_NAME="wazuh-proxy"

echo -e "${GREEN}✓ 脚本目录: $SERVICE_DIR${NC}"

# 1. 检查Python3
echo ""
echo "检查Python3..."
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}错误: Python3未安装${NC}"
    exit 1
fi
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo -e "${GREEN}✓ Python版本: $PYTHON_VERSION${NC}"

# 2. 创建虚拟环境
echo ""
echo "创建Python虚拟环境..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✓ 虚拟环境创建成功: $VENV_DIR${NC}"
else
    echo -e "${YELLOW}! 虚拟环境已存在，跳过创建${NC}"
fi

# 3. 安装依赖
echo ""
echo "安装Python依赖..."
source "$VENV_DIR/bin/activate"
pip install --upgrade pip > /dev/null
pip install -r "$SERVICE_DIR/requirements.txt"
echo -e "${GREEN}✓ 依赖安装完成${NC}"

# 4. 创建.env文件
echo ""
echo "配置环境变量..."
if [ ! -f "$SERVICE_DIR/.env" ]; then
    cp "$SERVICE_DIR/.env.example" "$SERVICE_DIR/.env"
    echo -e "${GREEN}✓ .env文件创建成功${NC}"
    echo -e "${YELLOW}! 请编辑 .env 文件设置正确的凭证${NC}"
else
    echo -e "${YELLOW}! .env文件已存在${NC}"
fi

# 5. 创建systemd服务文件
echo ""
echo "创建systemd服务..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=Wazuh API Proxy Service
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
WorkingDirectory=$SERVICE_DIR
Environment="PATH=$VENV_DIR/bin"
ExecStart=$VENV_DIR/bin/gunicorn -w 4 -b 0.0.0.0:5000 wazuh_proxy:app
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

echo -e "${GREEN}✓ systemd服务文件创建成功${NC}"

# 6. 重新加载systemd
echo ""
echo "重新加载systemd配置..."
systemctl daemon-reload
echo -e "${GREEN}✓ systemd配置重新加载完成${NC}"

# 7. 设置权限
echo ""
echo "设置文件权限..."
chown -R $SERVICE_USER:$SERVICE_USER "$SERVICE_DIR"
chmod +x "$SERVICE_DIR/wazuh_proxy.py"
echo -e "${GREEN}✓ 权限设置完成${NC}"

# 完成
echo ""
echo "=========================================="
echo -e "${GREEN}安装完成！${NC}"
echo "=========================================="
echo ""
echo "后续步骤："
echo ""
echo "1. 编辑配置文件（如果需要）："
echo "   vim $SERVICE_DIR/.env"
echo ""
echo "2. 启动服务："
echo "   sudo systemctl start $SERVICE_NAME"
echo ""
echo "3. 设置开机自启："
echo "   sudo systemctl enable $SERVICE_NAME"
echo ""
echo "4. 查看服务状态："
echo "   sudo systemctl status $SERVICE_NAME"
echo ""
echo "5. 查看日志："
echo "   sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "6. 测试服务："
echo "   curl http://localhost:5000/health"
echo ""
echo "=========================================="
