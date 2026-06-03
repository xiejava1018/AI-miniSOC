#!/bin/bash
# 智能启动脚本：从后端获取系统配置后启动前端

set -e

FRONTEND_DIR="$(dirname "$0")"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
ENV_FILE="$FRONTEND_DIR/.env.local"

echo "=== 前端智能启动脚本 ==="
echo "从后端获取系统配置: $BACKEND_URL"

# 获取系统配置
echo "获取 allowed_hosts 配置..."
ALLOWED_HOSTS=$(curl -s "$BACKEND_URL/api/v1/public/system-info" | \
    jq -r '.data.allowed_hosts // "all"' 2>/dev/null || echo "all")

echo "allowed_hosts: $ALLOWED_HOSTS"

# 写入 .env.local
cat > "$ENV_FILE" << ENV_EOF
# 从后端自动获取的配置 - $(date)
VITE_ALLOWED_HOSTS=$ALLOWED_HOSTS
ENV_EOF

echo "配置已写入: $ENV_FILE"
echo ""
echo "启动前端..."
cd "$FRONTEND_DIR"
npm run dev
