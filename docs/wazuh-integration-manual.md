# Wazuh集成配置指南

## 概述

本文档说明如何在Wazuh服务器上配置自定义集成，实现agent状态变化时自动触发miniSOC资产同步。

## 前提条件

- Wazuh服务器访问权限（192.168.0.30或192.168.0.40）
- 后端服务器IP：192.168.0.42
- 后端端口：8000

## 步骤1：自动化配置（推荐）

在Wazuh服务器上执行：

```bash
# 下载并运行配置脚本
scp /home/xiejava/AIproject/AI-miniSOC/scripts/wazuh-integration.sh root@192.168.0.30:/tmp/
ssh root@192.168.0.30 'bash /tmp/wazuh-integration.sh'
```

脚本会自动：
1. 生成安全的API Key
2. 创建集成脚本
3. 配置ossec.conf
4. 重启Wazuh manager

## 步骤2：手动配置

如果自动配置失败，请按以下步骤手动操作：

### 2.1 创建集成脚本

```bash
sudo tee /var/ossec/integrations/custom-minisoc << 'EOF'
#!/usr/bin/env python3
import sys
import json
import httpx
import logging

logging.basicConfig(filename='/var/log/wazuh/integrations.log', level=logging.INFO)

def main():
    alert_file = sys.argv[1]
    api_key = sys.argv[2]
    hook_url = sys.argv[3]

    with open(alert_file) as f:
        alert = json.load(f)

    agent_id = alert.get('agent', {}).get('id')

    payload = {
        "agent_id": agent_id,
        "agent_name": alert.get('agent', {}).get('name'),
        "rule_id": alert.get('rule', {}).get('id'),
        "alert": alert
    }

    response = httpx.post(
        hook_url,
        json=payload,
        headers={"X-API-Key": api_key},
        timeout=5
    )

    logging.info(f"Webhook sent for agent {agent_id}, status: {response.status_code}")

if __name__ == "__main__":
    main()
EOF

sudo chmod 750 /var/ossec/integrations/custom-minisoc
sudo chown root:wazuh /var/ossec/integrations/custom-minisoc
```

### 2.2 配置ossec.conf

```bash
# 备份
sudo cp /var/ossec/etc/ossec.conf /var/ossec/etc/ossec.conf.bak

# 添加integration配置
sudo tee -a /var/ossec/etc/ossec.conf << 'EOF'

  <!-- AI-miniSOC Integration -->
  <integration>
    <name>custom-minisoc</name>
    <hook_url>http://192.168.0.42:8000/api/v1/webhooks/wazuh</hook_url>
    <api_key>YOUR_API_KEY_HERE</api_key>
    <rule_id>504,506</rule_id>
    <alert_format>json</alert_format>
  </integration>
EOF
```

将`YOUR_API_KEY_HERE`替换为实际生成的密钥。

### 2.3 重启Wazuh

```bash
sudo systemctl restart wazuh-manager
sudo systemctl status wazuh-manager
```

## 步骤3：配置后端环境变量

在后端服务器上执行：

```bash
cd /home/xiejava/AIproject/AI-miniSOC/src/backend
echo "WAZUH_WEBHOOK_KEY=YOUR_API_KEY_HERE" >> .env
echo "WAZUH_WEBHOOK_ALLOWED_IPS=192.168.0.30,192.168.0.40" >> .env
```

## 步骤4：验证配置

### 4.1 检查Wazuh日志

```bash
sudo tail -f /var/log/wazuh/integrations.log
```

### 4.2 手动测试脚本

```bash
# 创建测试alert文件
cat > /tmp/test_alert.json << 'EOF'
{
  "agent": {"id": "001", "name": "test-server"},
  "rule": {"id": "504", "level": 3}
}
EOF

# 测试脚本
sudo -u wazuh /var/ossec/integrations/custom-minisoc /tmp/test_alert.json API_KEY http://192.168.0.42:8000/api/v1/webhooks/wazuh
```

### 4.3 触发真实测试

临时断开一个Wazuh agent：
```bash
# 在agent上
sudo systemctl stop wazuh-agent

# 检查miniSOC是否收到webhook（应该有新资产或状态更新）
```

## 故障排查

### 问题1：脚本无输出

**症状**：webhook没有触发

**解决方案**：
- 检查脚本权限：`ls -la /var/ossec/integrations/custom-minisoc`
- 应该是：`-rwxr-x---  root wazuh`

### 问题2：Webhook失败

**症状**：日志显示错误

**解决方案**：
- 检查网络连接：`curl http://192.168.0.42:8000/health`
- 检查API key是否匹配
- 检查后端日志：`tail -f /tmp/backend.log`

### 问题3：无触发

**症状**：agent状态变化但没有webhook

**解决方案**：
- 检查rule_id配置（504,506）
- 检查agent是否生成这些rule的告警
- 在Wazuh dashboard查看agent events

## 监控和维护

### 查看集成日志

```bash
sudo tail -f /var/log/wazuh/integrations.log
```

### 查看Wazuh manager状态

```bash
sudo systemctl status wazuh-manager
sudo journalctl -u wazuh-manager -f
```

### 修改配置

如果需要修改webhook URL或API key：

1. 编辑`/var/ossec/etc/ossec.conf`
2. 更新`<hook_url>`或`<api_key>`
3. 重启：`sudo systemctl restart wazuh-manager`

## 安全建议

1. **使用HTTPS**: 在生产环境中使用HTTPS webhook URL
2. **定期轮换密钥**: 每90天更换一次API key
3. **IP白名单**: 保持IP白名单更新
4. **日志审计**: 定期检查集成日志

## 相关文档

- [Wazuh External API Integration](https://documentation.wazuh.com/current/user-manual/manager/integration-with-external-apis.html)
- [Wazuh Agent Life Cycle](https://documentation.wazuh.com/current/user-manual/agent/agent-enrollment/agent-life-cycle.html)
- [项目实施计划](./superpowers/plans/2026-03-24-asset-sync-from-wazuh-plan.md)
