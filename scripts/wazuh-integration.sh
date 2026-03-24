#!/bin/bash
# Wazuh集成脚本
# 在Wazuh服务器(192.168.0.30)上执行此脚本

set -e

echo "=== Wazuh集成配置脚本 ==="
echo "此脚本将在Wazuh服务器上配置自定义集成，实现agent状态变化时自动触发miniSOC资产同步"

# 检查是否以root运行
if [ "$EUID" -ne 0 ]; then
    echo "请使用sudo运行此脚本"
    exit 1
fi

# 生成安全的API Key
API_KEY=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
echo "生成的API Key: $API_KEY"

# 创建集成脚本
echo "创建集成脚本..."
cat > /var/ossec/integrations/custom-minisoc << 'EOF'
#!/usr/bin/env python3
"""
Wazuh Integration Script for AI-miniSOC
触发资产同步Webhook
"""
import sys
import json
import httpx
import logging

logging.basicConfig(filename='/var/log/wazuh/integrations.log', level=logging.INFO)

def main():
    # 读取参数
    alert_file = sys.argv[1] if len(sys.argv) > 1 else None
    api_key = sys.argv[2] if len(sys.argv) > 2 else None
    hook_url = sys.argv[3] if len(sys.argv) > 3 else None

    if not alert_file or not hook_url:
        logging.error("Missing required parameters")
        sys.exit(1)

    # 解析alert
    try:
        with open(alert_file) as f:
            alert = json.load(f)
    except Exception as e:
        logging.error(f"Failed to read alert file: {e}")
        sys.exit(1)

    # 提取agent信息
    agent_id = alert.get('agent', {}).get('id')
    agent_name = alert.get('agent', {}).get('name')
    rule_id = alert.get('rule', {}).get('id')

    if not agent_id:
        logging.error("Agent ID not found in alert")
        sys.exit(1)

    # 调用miniSOC API
    try:
        payload = {
            "agent_id": agent_id,
            "agent_name": agent_name,
            "rule_id": rule_id,
            "alert": alert
        }

        headers = {}
        if api_key:
            headers["X-API-Key"] = api_key

        response = httpx.post(
            hook_url,
            json=payload,
            headers=headers,
            timeout=5
        )

        if response.status_code == 200:
            logging.info(f"Webhook sent successfully for agent {agent_id}")
        else:
            logging.warning(f"Webhook returned {response.status_code}: {response.text}")

    except Exception as e:
        logging.error(f"Failed to send webhook: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
EOF

# 设置权限
echo "设置脚本权限..."
chmod 750 /var/ossec/integrations/custom-minisoc
chown root:wazuh /var/ossec/integrations/custom-minisoc

# 备份配置
echo "备份Wazuh配置..."
cp /var/ossec/etc/ossec.conf /var/ossec/etc/ossec.conf.bak-$(date +%Y%m%d)

# 添加integration配置
echo "添加integration配置到ossec.conf..."
if ! grep -q "AI-miniSOC Integration" /var/ossec/etc/ossec.conf; then
    cat >> /var/ossec/etc/ossec.conf << 'EOF'

  <!-- AI-miniSOC Integration -->
  <integration>
    <name>custom-minisoc</name>
    <hook_url>http://192.168.0.42:8000/api/v1/webhooks/wazuh</hook_url>
    <api_key>${API_KEY}</api_key>
    <rule_id>504,506</rule_id>
    <alert_format>json</alert_format>
  </integration>
EOF
    echo "Integration配置已添加"
else
    echo "Integration配置已存在，跳过"
fi

# 更新后端环境变量
echo ""
echo "=== 重要：需要在后端服务器上执行以下命令 ==="
echo "cd /home/xiejava/AIproject/AI-miniSOC/src/backend"
echo "echo \"WAZUH_WEBHOOK_KEY=${API_KEY}\" >> .env"
echo "echo \"WAZUH_WEBHOOK_ALLOWED_IPS=192.168.0.30,192.168.0.40\" >> .env"

# 重启Wazuh manager
echo ""
echo "重启Wazuh manager..."
systemctl restart wazuh-manager
systemctl status wazuh-manager

echo ""
echo "=== Wazuh集成配置完成 ==="
echo "1. 集成脚本: /var/ossec/integrations/custom-minisoc"
echo "2. API Key: ${API_KEY}"
echo "3. 配置文件: /var/ossec/etc/ossec.conf"
echo "4. 日志文件: /var/log/wazuh/integrations.log"
echo ""
echo "下一步："
echo "- 在后端服务器上执行上述环境变量命令"
echo "- 测试webhook: 断开一个agent，检查miniSOC是否收到"
