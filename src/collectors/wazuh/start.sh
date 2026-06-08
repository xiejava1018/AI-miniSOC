#!/bin/bash
# Wazuh Collector 启动脚本

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="/home/xiejava/AIproject/AI-miniSOC/src/backend/venv/bin/python"

cd "$SCRIPT_DIR"

echo "Starting Wazuh Collector..."
echo "Config: $SCRIPT_DIR/config.yaml"

exec $VENV_PYTHON -m wazuh_collector --config "$SCRIPT_DIR/config.yaml"